"""Set size as a value, not a structure.

An N-object search array written as N separate `Show` actions makes set size a change
to the *shape* of the task -- a different task file for 4 objects and 8 objects, which
defeats the entire reason the model is declarative and makes the commonest
manipulation in visual search unavailable to live editing. Visual search is the
lab's programme, so this was not a small gap.
"""

import math

import pytest

from wl_xcon.check import check
from wl_xcon.task import (
    Array,
    Disc,
    ObjectWindows,
    On,
    After,
    Outcome,
    P,
    Param,
    SaccadeTo,
    Show,
    Square,
    State,
    Stimulus,
    Trial,
)


def test_set_size_is_a_parameter_the_array_expands_at_run_time():
    array = Array(n=P("set_size"), radius=8.0, target=P("target_index"))
    positions = array.positions({"set_size": 6, "target_index": 2})

    assert len(positions) == 6
    # Evenly spaced on a ring of the declared radius, in visual angle (the PI, 2026-10-19): about
    # straight ahead each object's bearing is `atan2(tan y, tan x)`.
    for x, y in positions:
        assert math.isclose(_apart((0.0, 0.0), (x, y)), 8.0, abs_tol=1e-9)
    angles = sorted(math.atan2(math.tan(math.radians(y)), math.tan(math.radians(x))) % (2 * math.pi)
                    for x, y in positions)
    gaps = [b - a for a, b in zip(angles, angles[1:])]
    assert all(math.isclose(g, 2 * math.pi / 6, abs_tol=1e-9) for g in gaps)


def test_the_target_wears_the_target_appearance_and_the_rest_do_not():
    array = Array(n=4, target=1, looks=Square(size=1.0), among=Disc(size=1.0))
    worn = [array.object_looks(i, {}) for i in range(4)]

    assert worn[1] == Square(size=1.0)
    assert worn[0] == worn[2] == worn[3] == Disc(size=1.0)


def test_a_target_index_outside_the_set_is_refused_over_the_whole_range():
    """Legal at the value someone tested, illegal at one the console can set.

    Set size and target index are both live parameters, so an experimenter can put
    the target at position 6 of a 4-object array between one trial and the next. The
    check reasons over declared *ranges*, which is the only way to catch it before
    it happens.
    """
    trial = Trial(
        start="on",
        windows=[ObjectWindows(of="search", radius=2.0)],
        params=[
            Param("set_size", unit="objects", low=2, high=8),
            Param("target_index", unit="index", low=0, high=11),
        ],
        states=[
            State(
                "on",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=P("set_size"), target=P("target_index")),
                        )
                    )
                ],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )
    assert "target-outside-array" in {f.code for f in check(trial)}


def test_the_array_generates_its_own_windows():
    """One declaration, n windows, because n is not known until a trial runs."""
    windows = ObjectWindows(of="search", radius=2.0).expand(
        Array(n=4, radius=8.0, target=1), {}
    )
    names = {w.name for w in windows}

    assert names == {
        "search.0",
        "search.1",
        "search.2",
        "search.3",
        "search.target",
        "search.distractor",
    }
    # The target alias sits where object 1 sits, not somewhere of its own.
    by_name = {w.name: w for w in windows}
    assert by_name["search.target"].at == by_name["search.1"].at
    # Every generated window scores the array, so the display check applies to
    # them exactly as it does to a hand-written window.
    assert all(w.on == "search" for w in windows)


def test_a_saccade_to_a_distractor_is_distinguishable_from_one_to_the_target():
    """The measurement search tasks exist to make.

    Without a distractor alias every error saccade would have to be enumerated as
    a separate transition per object -- which is n transitions, so it is the same
    structure-versus-value problem one level down.
    """
    from wl_xcon.run import Scripted, run_trial

    trial = Trial(
        start="search",
        windows=[ObjectWindows(of="search", radius=2.0)],
        params=[],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=4, radius=8.0, target=1),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    to_distractor = Scripted(at_frame={SaccadeTo("search.distractor"): 3})
    assert run_trial(trial, to_distractor, 0.01).outcome is Outcome.WRONG_TARGET

    to_target = Scripted(at_frame={SaccadeTo("search.target"): 3})
    assert run_trial(trial, to_target, 0.01).outcome is Outcome.CORRECT


def test_an_array_that_would_not_fit_on_the_display_is_refused():
    """Check 8, over an array's objects rather than one stimulus."""
    from wl_xcon.geometry import Geometry

    trial = Trial(
        start="on",
        windows=[ObjectWindows(of="search", radius=2.0)],
        params=[],
        states=[
            State(
                "on",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=4, radius=40.0, target=0),
                        )
                    )
                ],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )
    geometry = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
    )
    codes = {f.code for f in check(trial, geometry=geometry)}
    assert "stimulus-off-screen" in codes


def test_a_hold_on_an_alias_resolves_to_the_object_it_names():
    """`search.target` is where object 1 is, and the loop must know that.

    A saccade guard reaches the world directly, which judges an alias by its objects itself
    (`gaze.Tracked.happened`; `tests/test_gaze.py`).
    Membership guards -- entering, leaving, holding -- are derived by the loop from
    concrete windows, and an unresolved alias would simply never be satisfied: the
    animal fixates the target and the task waits forever.
    """
    from wl_xcon.run import run_trial
    from wl_xcon.task import Hold

    trial = Trial(
        start="search",
        windows=[ObjectWindows(of="search", radius=2.0)],
        params=[],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=4, radius=8.0, target=1),
                        )
                    )
                ],
                go=[
                    On(Hold("search.target", 0.02), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )

    class OnObject:
        """A world that knows only concrete object windows, as a rig would."""

        def __init__(self, held: str) -> None:
            self.held = held

        def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
            return window == self.held

        def happened(self, guard, state: str, frame: int) -> bool:
            return False

        def began(self, state: str, frame: int, by) -> None:
            pass

        def display(self, visible, frame: int) -> None:
            pass

        def signal(self, frame: int) -> str:
            return "ok"

    assert run_trial(trial, OnObject("search.1"), 0.01).outcome is Outcome.CORRECT
    assert run_trial(trial, OnObject("search.2"), 0.01).outcome is Outcome.NO_RESPONSE


def test_a_search_task_simulates():
    """The simulator must cope with windows it did not get from `trial.windows`."""
    from wl_xcon.simulate import Subject, simulate

    trial = Trial(
        start="search",
        windows=[ObjectWindows(of="search", radius=2.0)],
        params=[],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=4, radius=8.0, target=1),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    census = simulate(
        trial,
        # Not fully engaged, so some trials time out: with every trial engaged and
        # a 4/s saccade hazard over a 1 s window, NO_RESPONSE is unreachable.
        Subject(seed=3, engagement=0.85, hazards={SaccadeTo: 4.0}),
        trials=200,
        frame_period=1 / 240,
    )
    assert census.outcomes[Outcome.CORRECT] > 0
    assert census.uncovered(trial) == set()


# --- A true circle about the array's own direction (the PI, 2026-10-19: "True circle") -------
#
# "Every object exactly R from the array's center in visual angle, wherever the array is;
# spacing 2·asin(sin R·sin(π/n))." Every expectation here is computed from directions, `D · tan`
# per axis, with numpy's dot products: never with `geometry`'s own arithmetic.


def _unit(x: float, y: float):
    import numpy as np

    t = np.array([math.tan(math.radians(x)), math.tan(math.radians(y)), 1.0])
    return t / np.linalg.norm(t)


def _apart(p, q) -> float:
    """The angle at the eye between two positions; fine away from 0°."""
    import numpy as np

    return math.degrees(math.acos(float(np.clip(_unit(*p) @ _unit(*q), -1.0, 1.0))))


@pytest.mark.parametrize("at", [(0.0, 0.0), (10.0, 5.0), (20.0, 20.0)])
def test_every_object_is_its_ring_s_radius_from_the_array_s_center_in_visual_angle(at):
    """Wherever the array is, each of its objects is R degrees of visual angle from its center,
    and neighbors are `2·asin(sin R·sin(π/n))` apart at any phase (the PI, 2026-10-19). Per axis,
    an 8° ring's object at 45° about (0°, 0°) was 7.975° out."""
    array = Array(n=7, radius=8.0, target=0, phase=P("phase"))
    for phase in (0.0, 13.0, 45.0):
        positions = (array.positions({"phase": phase}) if at == (0.0, 0.0)
                     else array.positions({"phase": phase}, at=at))
        out = [_apart(at, p) for p in positions]
        spacing = [_apart(p, q) for p, q in zip(positions, positions[1:] + positions[:1])]

        assert out == pytest.approx([8.0] * 7, abs=1e-9)
        expected = math.degrees(2 * math.asin(math.sin(math.radians(8.0)) * math.sin(math.pi / 7)))
        assert spacing == pytest.approx([expected] * 7, abs=1e-9)


def test_the_object_at_phase_theta_is_theta_counter_clockwise_from_the_array_s_rightward_axis():
    """Which object sits where, pinned: object i is at `phase + 360 i / n` degrees counter-clockwise
    from the array's local rightward axis, in the frame a shape's orientation is drawn in
    (`viewport.local_true_angle`), so in that frame it is `(R cos θ, R sin θ)`."""
    import numpy as np

    from wl_xcon import viewport

    array = Array(n=5, radius=6.0, target=0, phase=30.0)
    c = viewport.center(10.0, 5.0)
    for i, (x, y) in enumerate(array.positions({}, at=(10.0, 5.0))):
        u, w = viewport.local_true_angle(np.array([_unit(x, y)]), c)
        theta = math.radians(30.0 + 360.0 * i / 5)
        assert (float(u[0]), float(w[0])) == pytest.approx(
            (6.0 * math.cos(theta), 6.0 * math.sin(theta)), abs=1e-9)


def test_each_object_s_window_is_where_the_object_is_drawn():
    """XC-397: an array at (10°, 5°) had its windows on its ring about (0°, 0°), at (3°, 0°),
    (0°, 3°), ..., while its objects were drawn at (13°, 5°), ... Each window `<of>.<i>` is
    now centered where `screen` draws object i, and the target's alias where the target is."""
    from _rig import DIRECT
    from wl_xcon import screen
    from wl_xcon.photometry import Gray
    from wl_xcon.task import expand_windows

    trial = Trial(
        start="on",
        windows=[ObjectWindows(of="search", radius=1.0)],
        params=[Param("x", unit="deg", low=0.0, high=20.0), Param("phase", unit="deg", low=0.0,
                                                                   high=360.0)],
        states=[State("on", enter=[Show(Stimulus(
            "search", at=(P("x"), 5.0),
            looks=Array(n=4, radius=3.0, target=2, phase=P("phase"),
                        looks=Disc(size=0.5, color=Gray(40.0)),
                        among=Disc(size=0.5, color=Gray(40.0)))))],
            go=[On(SaccadeTo("search.target"), Outcome.CORRECT),
                On(After(1.0), Outcome.NO_RESPONSE)])],
    )
    values = {"x": 10.0, "phase": 20.0}

    windows = {w.name: w.at for w in expand_windows(trial, values)[0]}
    drawn = screen.resolve({"search": trial.states[0].enter[0].stimulus}, values, trial, DIRECT,
                           frame_period=1 / 240)

    for item in drawn.items:
        assert windows[item.name] == pytest.approx(item.at_left, abs=1e-12)
        assert _apart((10.0, 5.0), windows[item.name]) == pytest.approx(3.0, abs=1e-9)
    assert windows["search.target"] == windows["search.2"]


@pytest.mark.parametrize("height, shown", [(9.5, True), (10.2, False)])
def test_check_8_reads_an_array_s_true_circle_where_it_reaches_on_the_panel(height, shown):
    """An 8° ring about (20°, `height`°) in direct view, whose field reaches 18.41° up. About its
    own direction the ring reaches 8.50° up there, not 8°: at 10.2° it crosses the field's top
    edge, at 18.70°, where a per-axis square of ±8° stayed inside at 18.2°, and at 9.5° it stays
    in at 18.00°. Check 8 refuses it exactly when some phase puts an object past the edge, by the
    positions `Array.positions` gives."""
    from _rig import DIRECT

    trial = Trial(
        start="on",
        params=[Param("phase", unit="deg", low=0.0, high=360.0)],
        states=[State("on", enter=[Show(Stimulus("ring", at=(20.0, height), looks=Array(
            n=8, radius=8.0, target=0, phase=P("phase"), looks=Disc(size=0.5),
            among=Disc(size=0.5))))], go=[On(After(1.0), Outcome.ABORT)])],
    )
    reached = [p for phase in range(0, 360, 2)
               for p in Array(n=8, radius=8.0, target=0, phase=float(phase)).positions(
                   {}, at=(20.0, height))]

    refused = "stimulus-off-screen" in {f.code for f in check(trial, geometry=DIRECT)}

    assert all(DIRECT.can_show(*p) for p in reached) is shown
    assert refused is not shown


def test_the_aliases_name_the_target_and_every_other_object():
    """`<of>.target` is the target's window and `<of>.distractor` every other object's, for the
    set size the trial runs at."""
    members = ObjectWindows(of="search", radius=1.0).members(
        Array(n=P("set_size"), radius=8.0, target=P("target_index")),
        {"set_size": 6, "target_index": 2})

    assert members == {"search.target": ("search.2",),
                       "search.distractor": ("search.0", "search.1", "search.3", "search.4",
                                             "search.5")}


# --- An `Update`'s array is checked as a `Show`'s is (XC-402's review, I1 and I2) ----------------
#
# Since XC-402 an array's object windows follow an `Update` that changes it, so the array an
# `Update` gives is scored exactly as a `Show`'s is, and is held to the same load checks.


def _updated(update, windows_radius: float = 1.0, params=(), held: str = "search.1") -> Trial:
    """A four-object array on a 3° ring, then `update`, then 0.5 s for a hold on `held`."""
    from wl_xcon.task import Hold

    ring = Array(n=4, radius=3.0, target=1)
    return Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=windows_radius)],
        params=list(params),
        states=[
            State("shown", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=ring))],
                  go=[On(After(0.04), "changed")]),
            State("changed", enter=[update],
                  go=[On(Hold(held, 0.05), Outcome.CORRECT),
                      On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )


def test_an_update_whose_target_is_not_one_of_its_objects_is_refused_at_load():
    """As a `Show`'s is: built at a trial's start, its target window would raise there."""
    from wl_xcon.task import Update

    literal = _updated(Update("search", looks=Array(n=4, radius=3.0, target=7)))
    ranged = _updated(Update("search", looks=Array(n=4, radius=3.0, target=P("t"))),
                      params=[Param("t", unit="index", low=0, high=6)])

    for trial in (literal, ranged):
        refused = [f for f in check(trial) if f.code == "target-outside-array"]
        assert len(refused) == 1 and refused[0].blocking
        assert refused[0].detail.startswith("state 'changed' updates 'search' to an array of as few")


def test_an_update_that_crowds_its_array_is_warned_at_load():
    """Four objects on a 0.6° ring, 0.85° apart, with 1° windows: a saccade to one would be scored
    against another, after the update as before it."""
    from wl_xcon.task import Update

    warned = [f for f in check(_updated(Update("search", looks=Array(n=4, radius=0.6))))
              if f.code == "crowded-array"]

    assert len(warned) == 1 and not warned[0].blocking and warned[0].accepted_in
    assert "0.6° ring" in warned[0].detail


def test_an_object_window_asked_after_an_update_draws_no_array_is_warned():
    """`Update(looks=Blank())` leaves the windows where the objects were last drawn, and gaze there
    is scored as on them: right for a memory-guided design, wrong if not meant. A `Hide` is refused
    instead (`nothing-to-look-at`). Asked before the update, or after one that draws an array, it is
    not warned."""
    from wl_xcon.findings import SESSION_KINDS
    from wl_xcon.task import Blank, Update

    def codes(trial):
        return {f.code for f in check(trial)}

    blanked = [f for f in check(_updated(Update("search", looks=Blank())))
               if f.code == "windows-left-behind"]
    assert len(blanked) == 1
    assert not blanked[0].blocking and blanked[0].accepted_in == SESSION_KINDS
    assert "'search.1'" in blanked[0].detail and "last drawn" in blanked[0].detail
    assert "windows-left-behind" in codes(_updated(Update("search", looks=Blank()),
                                                   held="search.distractor"))
    assert "windows-left-behind" not in codes(_updated(Update("search", looks=Array(n=4))))
    assert "windows-left-behind" not in codes(_updated(Update("search", looks=Blank()),
                                                       held="fix"))


def test_an_object_window_asked_after_a_show_draws_no_array_is_warned():
    """The same for a `Show`: shown, hidden, and shown again as `Blank()`, the array draws no
    objects, so its windows stay where the objects were last drawn (the round-1 re-review). Shown
    again as an array, it is not warned."""
    from wl_xcon.task import Blank, Hide, Hold

    def again(looks) -> Trial:
        ring = Array(n=4, radius=3.0, target=1)
        return Trial(
            start="shown",
            windows=[ObjectWindows(of="search", radius=1.0)],
            states=[
                State("shown", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=ring))],
                      go=[On(After(0.04), "hidden")]),
                State("hidden", enter=[Hide("search")], go=[On(After(0.04), "again")]),
                State("again", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=looks))],
                      go=[On(Hold("search.1", 0.05), Outcome.CORRECT),
                          On(After(0.5), Outcome.NO_RESPONSE)]),
            ],
        )

    warned = [f for f in check(again(Blank())) if f.code == "windows-left-behind"]
    assert len(warned) == 1 and not warned[0].blocking
    assert "windows-left-behind" not in {f.code for f in check(again(Array(n=4, radius=3.0)))}


# --- An array drawn per eye is scored at its cyclopean position (XC-412) -------------------------
#
# An array's object windows stay on a ring about its cyclopean position, `at`, whatever per-eye
# positions or disparity it is drawn with (EYE-29, choice 5). With per-eye positions the screen
# draws nothing there; with a disparity each eye's image is half of it to one side. A task scoring
# an object window then is warned at load, in every kind.


def _per_eye(shown: dict, update=None, held: str = "search.1", params=()) -> Trial:
    """A four-object array on a 3° ring on the stereoscope, shown with `shown` -- a position per
    eye, a disparity, or neither -- then after 0.04 s `update`, if any, and 0.5 s for a hold on
    `held`."""
    from wl_xcon.task import Hold

    ring = Array(n=4, radius=3.0, target=1)
    return Trial(
        start="shown",
        view="stereoscope",
        windows=[ObjectWindows(of="search", radius=1.0)],
        params=list(params),
        states=[
            State("shown", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=ring, **shown))],
                  go=[On(After(0.04), "held")]),
            State("held", enter=[update] if update is not None else [],
                  go=[On(Hold(held, 0.05), Outcome.CORRECT),
                      On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )


def _cyclopean(trial: Trial) -> list:
    return [f for f in check(trial) if f.code == "cyclopean-windows"]


#: Each eye's own position, 1° either side of straight ahead.
_EACH_EYE = {"at_left": (-1.0, 0.0), "at_right": (1.0, 0.0)}


def test_an_object_window_of_an_array_drawn_per_eye_is_warned_where_it_is():
    """Scored where the screen draws nothing, a warning in every kind that says where the windows
    are and why the animal may not be looking there; for an object, and for an alias."""
    from wl_xcon.findings import SESSION_KINDS

    found = _cyclopean(_per_eye(_EACH_EYE))

    assert len(found) == 1
    warned = found[0]
    assert not warned.blocking and warned.accepted_in == SESSION_KINDS
    assert warned.detail.startswith("state 'held' scores 'search.1', an object window of array "
                                    "'search', which can be drawn with a position per eye;")
    assert "cyclopean position" in warned.detail and "draws nothing" in warned.detail
    assert len(_cyclopean(_per_eye(_EACH_EYE, held="search.distractor"))) == 1


@pytest.mark.parametrize("disparity, params", [
    (0.5, ()),
    (P("d"), (Param("d", unit="deg", choices=(0.0, 0.4)),)),
], ids=["written", "among a setting's choices"])
def test_an_object_window_of_an_array_drawn_with_a_disparity_is_warned(disparity, params):
    """Each eye's image half the disparity to one side of where the windows are."""
    found = _cyclopean(_per_eye({"disparity": disparity}, params=params))

    assert len(found) == 1
    assert "which can be drawn with a disparity;" in found[0].detail
    assert "half the disparity" in found[0].detail


@pytest.mark.parametrize("update", [
    "per-eye positions", "a disparity",
])
def test_an_update_that_draws_the_array_per_eye_is_warned_after_it_and_not_before(update):
    """A may analysis along the task's paths, as `windows-left-behind`'s: an object window scored
    after an `Update` gives the array per-eye positions or a disparity is warned; one scored only
    before it is not."""
    from wl_xcon.task import Hold, Update

    given = (Update("search", **_EACH_EYE) if update == "per-eye positions"
             else Update("search", disparity=0.3))
    before = Trial(
        start="held",
        view="stereoscope",
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[
            State("held", enter=[Show(Stimulus("search", at=(0.0, 0.0),
                                                looks=Array(n=4, radius=3.0, target=1)))],
                  go=[On(Hold("search.1", 0.05), "given"), On(After(0.5), Outcome.NO_RESPONSE)]),
            State("given", enter=[given], go=[On(After(0.1), Outcome.CORRECT)]),
        ],
    )

    assert len(_cyclopean(_per_eye({}, update=given))) == 1
    assert _cyclopean(before) == []


def test_an_array_drawn_at_its_own_position_is_not_warned():
    """Controls: no per-eye position and no disparity, or a disparity provably zero, or per-eye
    positions cleared by an update that gives `at` again, or an array drawn per eye whose object
    windows nothing scores."""
    from wl_xcon.task import Update

    cleared = Update("search", at=(0.0, 0.0), at_left=None, at_right=None)
    for trial in (
        _per_eye({}),
        _per_eye({"disparity": 0.0}),
        _per_eye({"disparity": P("d")}, params=[Param("d", unit="deg", choices=(0.0,))]),
        _per_eye(_EACH_EYE, update=cleared),
        _per_eye(_EACH_EYE, held="fix"),
    ):
        assert _cyclopean(trial) == []


# --- An object only an `Update`'s array has is declared, and reviewed (XC-411) -------------------


def _grown(held: str) -> Trial:
    """A lit four-object array on a 5° ring, grown to eight objects by an `Update`, then 0.5 s for
    a hold on `held`."""
    from dataclasses import replace

    from wl_xcon.photometry import Gray
    from wl_xcon.task import Hold, Update

    lit = Disc(size=0.5, color=Gray(40.0))
    ring = Array(n=4, radius=5.0, target=1, looks=lit, among=lit)
    return Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[
            State("shown", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=ring))],
                  go=[On(After(0.04), "grown")]),
            State("grown", enter=[Update("search", looks=replace(ring, n=8))],
                  go=[On(Hold(held, 0.05), Outcome.CORRECT),
                      On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )


def test_an_object_only_an_update_s_array_has_is_declared():
    """Object 5 exists once an `Update` grows the array to eight, and a run scores it there
    (XC-402), so a hold on it loads clean: it was refused as undeclared, the checker reading only a
    `Show`'s array. Object 8 is past every array the task gives, and stays undeclared."""
    assert [f.code for f in check(_grown("search.5")) if f.blocking] == []
    assert "undeclared-window" in {f.code for f in check(_grown("search.8"))}


def test_an_object_of_an_array_a_setting_gives_is_declared_as_far_as_its_choices_reach():
    """Read as the run reads it (`task.placements`), an array a setting gives has the objects of
    each of its choices: object 5 of a choice of six is declared, and object 6 is not. Neither was
    declared while the checker read only an array written into a `Show` (XC-411)."""
    from wl_xcon.photometry import Gray
    from wl_xcon.task import Hold

    lit = Disc(size=0.5, color=Gray(40.0))

    def held(name: str) -> Trial:
        return Trial(
            start="shown",
            params=[Param("ring", unit="array", choices=(
                Array(n=4, radius=5.0, looks=lit, among=lit),
                Array(n=6, radius=5.0, looks=lit, among=lit)))],
            windows=[ObjectWindows(of="search", radius=1.0)],
            states=[State("shown", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=P("ring")))],
                          go=[On(Hold(name, 0.05), Outcome.CORRECT),
                              On(After(0.5), Outcome.NO_RESPONSE)])],
        )

    assert [f.code for f in check(held("search.5")) if f.blocking] == []
    assert "undeclared-window" in {f.code for f in check(held("search.6"))}
