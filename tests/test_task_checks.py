"""The load-time checks from S1 §9.

A task that fails any of these is refused at load, not at run. The point is that a
generated task is caught before an animal sees it -- pitfalls P15.
"""

import pytest

from wl_xcon.task import (
    RDS,
    Corrugation,
    Disc,
    REMEMBERED,
    After,
    Array,
    Entered,
    Bounded,
    Custom,
    Exited,
    Hold,
    ObjectWindows,
    On,
    Outcome,
    P,
    Param,
    Mark,
    Response,
    Reward,
    SaccadeTo,
    Show,
    State,
    Stimulus,
    Update,
    Window,
    Trial,
)
from wl_xcon.check import _declared_window_names, check
from wl_xcon.findings import SESSION_KINDS
from dataclasses import replace

# `GEOMETRY` is the rig's stereoscope at the drawing's `E` = 1.6 cm: a 63.15 cm path, and
# the ±13.15° × ±14.77° viewport stopped by the PI's ±12° mask. `DIRECT` is the rig in
# direct view. Both are `tests/_rig.py`'s, with its stand-in housings.
from _rig import DIRECT, STEREOSCOPE as GEOMETRY
from wl_xcon.codes import PROVISIONAL, Allocation
from wl_xcon.components import Registry
from wl_xcon.geometry import Geometry
from wl_xcon.photometry import Gray

LIT = Disc(color=Gray(40.0))


def test_a_state_no_transition_can_reach_is_reported():
    """S1 §9 check 2. A state nothing reaches is dead code in a task, and in a
    generated task it is the shape a hallucinated state name takes."""
    trial = Trial(
        start="await_fix",
        states=[
            State("await_fix", go=[On(After(4.0), Outcome.NO_FIXATION)]),
            State("orphan", go=[On(After(1.0), Outcome.CORRECT)]),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["unreachable-state"]
    assert "orphan" in findings[0].detail
    # A review note, never a refusal (XC-352's A7; the PI, 2026-10-11): `wlx check` shows it,
    # and no session refuses or asks it.
    assert (findings[0].blocking, findings[0].accepted_in) == (False, ())
    assert findings[0].detail.endswith("which is probably a mistake")


def test_a_state_with_no_time_bound_is_reported_as_an_unbounded_wait():
    """S1 §9 check 4, and the defect the S1 bake-off actually produced: a
    fixation hold that can wait forever. Every wait needs a bound or an
    explicit declaration that it has none."""
    trial = Trial(
        start="hold_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State(
                "hold_fix",
                go=[On(Exited("fix"), Outcome.FIXATION_BREAK)],
            ),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["unbounded-wait"]
    assert "hold_fix" in findings[0].detail


def test_a_state_declaring_itself_unbounded_is_accepted():
    """Free viewing of natural images is a first-class unbounded epoch (S1 §5.4).
    The check exists to make it deliberate and visible, not to forbid it."""
    trial = Trial(
        start="free_view",
        states=[
            State(
                "free_view",
                go=[On(Response("lever"), Outcome.CORRECT)],
                unbounded=True,
            ),
        ],
    )

    assert check(trial) == []


def test_a_reward_action_refuses_a_magnitude():
    """S1 §2.3 and S8 §4. A task may name a bounded-config entry; it may not say
    how much. The ceiling is enforced by what the task can express, not by review
    noticing -- which matters because the task was probably written by a model.

    A type checker catches this too. The runtime refusal is the one that catches
    a generated task at load, on a machine with no type checker running.
    """
    with pytest.raises(TypeError, match="bounded-config"):
        Reward(0.15)


def test_a_reward_action_names_a_bounded_config_entry():
    assert Reward(Bounded("reward_small")).ref.name == "reward_small"


def test_states_that_cannot_reach_an_outcome_are_reported():
    """S1 §9 check 3. A trial that can enter a loop with no exit to an outcome
    never scores, never ends, and never tells anyone why -- it just stops
    producing trials while looking like it is running."""
    trial = Trial(
        start="ping",
        states=[
            State("ping", go=[On(After(1.0), "pong")]),
            State("pong", go=[On(After(1.0), "ping")]),
        ],
    )

    findings = check(trial)

    assert {f.code for f in findings} == {"no-outcome-path"}
    assert {"ping", "pong"} == {f.detail.split("'")[1] for f in findings}


def test_a_transition_shadowed_by_an_earlier_identical_guard_is_reported():
    """S1 §9 check 10, in the form it takes once transitions fire in declared
    order (M0 §4): with order defined there is no ambiguity to detect, but a
    repeated guard means the later transition can never fire. That is dead code,
    and duplicating a guard is a shape a generated task produces readily."""
    trial = Trial(
        start="decide",
        states=[
            State(
                "decide",
                go=[
                    On(After(1.0), Outcome.NO_RESPONSE),
                    On(After(1.0), Outcome.CORRECT),
                ],
            ),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["shadowed-transition"]
    assert "decide" in findings[0].detail
    assert (findings[0].blocking, findings[0].accepted_in) == (False, ())
    assert findings[0].detail.endswith("which is probably a mistake")


def test_a_task_emitting_an_unallocated_code_is_refused():
    """S1 §9 check 1, and the cheapest guardrail in the design against a
    model-authored task (P15). A model will emit a plausible-looking number; the
    allocation is the only thing that knows 4097 means nothing."""
    allocation = replace(PROVISIONAL, task_events={4096: "STIMULUS_ON"})
    trial = Trial(
        start="show",
        states=[
            State(
                "show",
                enter=[Mark(4097)],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, allocation)

    assert [f.code for f in findings] == ["unallocated-code"]
    assert "4097" in findings[0].detail


def test_a_task_emitting_an_allocated_code_is_accepted():
    allocation = replace(PROVISIONAL, task_events={4096: "STIMULUS_ON"})
    trial = Trial(
        start="show",
        states=[
            State(
                "show",
                enter=[Mark(4096)],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert check(trial, allocation) == []


def test_a_task_referencing_an_undeclared_parameter_is_refused():
    """S1 §9 check 6. Parameters are declared with type, unit and range (S8 §3.1),
    and that one declaration drives validation, the console's widgets and the saved
    record. A reference to something undeclared has no widget, no range and no
    snapshot -- so it would be live-editable to any value, or not editable at all,
    and nobody would know which."""
    trial = Trial(
        start="hold",
        params=[Param("fix_hold", unit="s", low=0.1, high=2.0)],
        states=[
            State("hold", go=[On(After(P("response_deadline")), Outcome.NO_RESPONSE)]),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["undeclared-parameter"]
    assert "response_deadline" in findings[0].detail


def test_a_task_referencing_a_declared_parameter_is_accepted():
    trial = Trial(
        start="hold",
        params=[Param("fix_hold", unit="s", low=0.1, high=2.0)],
        states=[
            State("hold", go=[On(After(P("fix_hold")), Outcome.NO_RESPONSE)]),
        ],
    )

    assert check(trial) == []


def test_a_custom_component_that_does_not_resolve_is_refused():
    """S1 §9 check 9, and what makes S1 §8's typed seam real. A task may name
    behaviour the vocabulary lacks, but that behaviour lives in the framework's
    own reviewed source -- not in the task file. A name that resolves to nothing
    is the seam being used as a hole."""
    trial = Trial(
        start="stabilise",
        states=[
            State(
                "stabilise",
                enter=[Custom("retinal_stabilisation")],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, components=Registry({}))

    assert [f.code for f in findings] == ["unresolved-custom-component"]
    assert "retinal_stabilisation" in findings[0].detail


def test_a_resolving_custom_component_is_accepted_but_flagged_for_review():
    """S1 §8: a task using a Custom component goes on the human-review list beside
    the welfare-critical modules. Accepted is not the same as unremarkable."""
    registry = Registry({"retinal_stabilisation": "reviewed 2026-08-31"})
    trial = Trial(
        start="stabilise",
        states=[
            State(
                "stabilise",
                enter=[Custom("retinal_stabilisation")],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, components=registry)

    assert [f.code for f in findings] == ["custom-component-needs-review"]
    assert findings[0].blocking is False


def test_a_stimulus_outside_the_field_is_refused():
    """S1 §9 check 8. Asked for a peripheral target, a model will write 30 degrees
    as readily as 10. The stimulus would be drawn off the panel, the animal would
    never see it, and the trial would score as a miss indistinguishable from
    behaviour -- which is the worst kind of defect, because the data looks fine."""
    trial = Trial(
        start="show",
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(30.0, 0.0), looks=LIT))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, geometry=GEOMETRY)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "30" in findings[0].detail


def test_disparity_can_push_one_eye_off_screen_from_a_legal_cyclopean_position():
    """The stereo defect a monocular check cannot see. Disparity is applied as
    equal and opposite horizontal offsets about the cyclopean position, so a
    stimulus comfortably inside the field can still put one eye's image outside
    it -- and only that eye's. On a split-screen stereoscope that is a stimulus
    the animal fuses on one side and loses on the other."""
    trial = Trial(
        start="show",
        view="stereoscope",
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(10.0, 0.0), disparity=-2.0, looks=LIT))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert GEOMETRY.can_show(10.0 + GEOMETRY.vergence_half_deg, 0.0), (
        "both eyes' images are legal without disparity"
    )

    findings = check(trial, geometry=GEOMETRY)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "disparity" in findings[0].detail


def test_a_terminal_outcome_with_no_allocated_marker_is_refused():
    """S1 §9 check 5. An outcome that maps to no marker is a trial that ends
    without saying how it ended -- the recording carries the timing of a decision
    whose result is only in our files."""
    allocation = Allocation(outcomes={Outcome.CORRECT: 34})
    trial = Trial(
        start="decide",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State(
                "decide",
                go=[
                    On(After(1.0), Outcome.CORRECT),
                    On(Exited("fix"), Outcome.FIXATION_BREAK),
                ],
            ),
        ],
    )

    findings = check(trial, allocation)

    assert [f.code for f in findings] == ["unallocated-outcome"]
    assert "FIXATION_BREAK" in findings[0].detail


def test_actions_on_a_transition_are_checked_too():
    """Found by writing the first real task, which the checker passed while
    emitting an unallocated code.

    Actions live in two places -- on state entry and on a transition -- and every
    check that walks actions must walk both. Reward in particular can only ever be
    a transition action, because a terminal outcome has no state to enter, so a
    checker blind to transitions is blind to exactly the actions that score.
    """
    trial = Trial(
        start="decide",
        states=[
            State(
                "decide",
                go=[On(After(1.0), Outcome.CORRECT, do=[Mark(4097)])],
            ),
        ],
    )

    findings = check(trial, replace(PROVISIONAL, task_events={4096: "STIMULUS_ON"}))

    assert [f.code for f in findings] == ["unallocated-code"]
    assert "4097" in findings[0].detail


def test_a_task_referencing_an_undeclared_window_is_refused():
    """S1a §1. A task naming `"fix"` as a gaze window while nothing says where it
    is or how large has no fixation criterion at all -- and position and size are
    exactly what an experimenter tunes, so they cannot be implicit."""
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("target"), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )

    findings = check(trial)

    assert [f.code for f in findings] == ["undeclared-window"]
    assert "target" in findings[0].detail


def test_a_position_parameter_whose_range_leaves_the_field_is_refused():
    """Stronger than checking one value. At load there is no value -- there is a
    declared range, and every value in it is one an experimenter can dial in live
    (S8 §3). So the check proves the task *cannot* place a stimulus off-screen for
    any legal setting, rather than that it happens not to today."""
    trial = Trial(
        start="show",
        params=[Param("ecc", unit="deg", low=-20.0, high=20.0)],
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(P("ecc"), 0.0), looks=LIT))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    findings = check(trial, geometry=GEOMETRY)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "ecc" in findings[0].detail


def test_a_position_parameter_whose_range_stays_inside_the_field_is_accepted():
    trial = Trial(
        start="show",
        params=[Param("ecc", unit="deg", low=-10.5, high=10.5)],
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(P("ecc"), 0.0), looks=LIT))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )

    assert check(trial, geometry=GEOMETRY) == []


# ---------------------------------------------------------------------------
# Check 8 against each setup's own field (direct-view spec §2, §4)
# ---------------------------------------------------------------------------


def _showing(at, params=(), **fields) -> Trial:
    """One state showing stimulus `s` at `at`, with any other `Stimulus` fields."""
    return Trial(
        start="show",
        params=list(params),
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=at, **{"looks": LIT, **fields}))],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )


def test_a_stimulus_under_a_light_sensors_housing_is_refused_in_direct_view():
    """Direct-view spec §4: "check 8 refuses a stimulus that could overlap a housing,
    exactly as it refuses one off the panel." The position is on the panel; the
    housing covers it."""
    findings = check(_showing((-29.0, -17.0)), geometry=DIRECT)

    assert [f.code for f in findings] == ["stimulus-off-screen"]
    assert "direct field, less the light sensors' housings" in findings[0].detail


def test_a_range_that_can_reach_a_housing_is_refused():
    """Over the declared range, as check 8 always reasons: a target an experimenter
    can slide into the corner is refused before anyone does."""
    trial = _showing(
        (P("x"), -17.0), params=[Param("x", unit="deg", low=-29.0, high=0.0)]
    )

    assert [f.code for f in check(trial, geometry=DIRECT)] == ["stimulus-off-screen"]
    assert check(_showing((P("x"), 0.0), trial.params), geometry=DIRECT) == []


def test_direct_view_shows_what_the_stereoscopes_mask_stops():
    """The reference detection tasks' ±16°, which the interim narrowed to ±12° for the
    stereoscope. Direct view takes it; the mask refuses it, and says which field."""
    trial = _showing((P("ecc"), 0.0), params=[Param("ecc", unit="deg", low=-16.0, high=16.0)])

    assert check(trial, geometry=DIRECT) == []
    (finding,) = check(trial, geometry=GEOMETRY)
    assert finding.code == "stimulus-off-screen"
    assert "±12.0° × ±12.0° stereoscope field" in finding.detail


def test_the_mask_refuses_what_the_bare_viewport_would_show():
    """Held to the rig's field, not the optics': 11.5° puts the left eye's image at
    12.95°: inside the viewport's ±13.15° and behind the mask."""
    viewport = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
    )

    assert check(_showing((11.5, 0.0)), geometry=viewport) == []
    assert [f.code for f in check(_showing((11.5, 0.0)), geometry=GEOMETRY)] == [
        "stimulus-off-screen"
    ]


# ---------------------------------------------------------------------------
# Check 8 fails closed: every value a parameter offers, and every Update
# (XC-036 to XC-038, carried from direct view part 1's final review)
# ---------------------------------------------------------------------------


def _off(trial, geometry=GEOMETRY) -> list:
    return [f for f in check(trial, geometry=geometry) if f.code == "stimulus-off-screen"]


def test_a_whole_position_parameter_is_checked_at_every_point_it_offers():
    """XC-036: `Stimulus(at=P("pos"))` crashed check 8 with a `TypeError`, indexing a
    parameter as if it were a pair, and would have crashed `taskd`'s load the day it
    passed a geometry. A position chosen among points is checked at each of them."""
    near = [Param("pos", unit="deg", choices=((0.0, 0.0), (5.0, -5.0)))]
    far = [Param("pos", unit="deg", choices=((0.0, 0.0), (30.0, 0.0)))]

    assert _off(_showing(P("pos"), near)) == []
    (finding,) = _off(_showing(P("pos"), far))
    assert "pos" in finding.detail
    assert f"{30.0 + GEOMETRY.vergence_half_deg:.1f}" in finding.detail


def test_a_whole_position_parameter_that_offers_no_points_is_refused():
    """A range, or choices that are not (x, y) points, names no place check 8 can
    test. It cannot be proved on screen, so it is refused rather than passed."""
    for param in (
        Param("pos", unit="deg", low=0.0, high=1.0),
        Param("pos", unit="deg", choices=(1.0, 2.0)),
    ):
        (finding,) = _off(_showing(P("pos"), [param]))
        assert "cannot be bounded" in finding.detail, param


def test_a_coordinate_declared_by_choices_is_checked_at_every_choice():
    """XC-038: a coordinate chosen among values was read as 0, the one place every
    field contains, so a choice of 30 degrees passed."""
    assert _off(_showing((P("x"), 0.0), [Param("x", unit="deg", choices=(0.0, 5.0))])) == []
    (finding,) = _off(_showing((P("x"), 0.0), [Param("x", unit="deg", choices=(0.0, 30.0))]))
    assert f"{30.0 + GEOMETRY.vergence_half_deg:.1f}" in finding.detail


def test_a_coordinate_with_no_two_sided_range_is_refused_rather_than_read_as_zero():
    """XC-038: no range, half a range, or no declaration at all can each be dialled
    anywhere, and each was read as 0. Undeclared is also `undeclared-parameter`'s to
    report; check 8 refuses what it cannot bound either way."""
    for params in ([Param("x", unit="deg")], [Param("x", unit="deg", low=-5.0)], []):
        (finding,) = _off(_showing((P("x"), 0.0), params))
        assert "'x'" in finding.detail and "cannot be bounded" in finding.detail, params


def test_a_disparity_declared_by_choices_is_checked_at_every_choice():
    """XC-038's disparity half. 3 degrees of near disparity at 10 puts the left eye's
    image past the mask."""
    safe = [Param("d", unit="deg", choices=(0.0, 0.4))]
    wide = [Param("d", unit="deg", choices=(0.0, -3.0))]

    assert _off(_showing((10.0, 0.0), safe, disparity=P("d"))) == []
    assert len(_off(_showing((10.0, 0.0), wide, disparity=P("d")))) == 1


def test_an_array_radius_declared_by_choices_is_checked_at_every_choice():
    """An object ring whose radius is chosen among values reaches as far as the
    largest; read as 0, it was only ever its centre."""
    ring = [Param("r", unit="deg", choices=(4.0, 20.0))]

    assert len(_off(_showing((0.0, 0.0), ring, looks=Array(radius=P("r"))))) == 1


def _searching(params, n, target, *named) -> Trial:
    """An array of `n` objects on a ring 8° out, its target the one `target` indexes, and a state
    holding each object window in `named`."""
    return Trial(
        start="search",
        params=list(params),
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[State("search", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=Array(
            n=n, radius=8.0, target=target, looks=LIT, among=LIT)))], go=[
            *(On(Hold(name, 0.1), Outcome.CORRECT) for name in named),
            On(SaccadeTo("search.target"), Outcome.CORRECT),
            On(After(1.0), Outcome.NO_RESPONSE),
        ])],
    )


def _finding(trial, code):
    return [f for f in check(trial) if f.code == code]


def test_an_arrays_target_and_a_correlation_are_read_over_their_choices_and_one_bound_never_as_zero():
    """Task 10's review, fix round 2: `_widest` read a setting with no two-sided range -- one
    bound, or choices -- as 0 to 0. A target index chosen from 0 and 5 of four objects, one with
    no highest, and a correlation chosen from 0.5 and 2 each passed at load, and each breaks a
    trial; a set size chosen from 4 and 8 was refused, read as no objects. Each is read over
    its choices, or over what its undeclared side can reach (`_span`)."""
    (chosen,) = _finding(_searching([Param("t", unit="index", choices=(0, 5))], 4, P("t")),
                         "target-outside-array")
    (endless,) = _finding(_searching([Param("t", unit="index", low=0)], 4, P("t")),
                          "target-outside-array")
    stereogram = replace(_task(Show(Stimulus("rds", at=(0.0, 0.0), looks=RDS(correlation=P("c"))))),
                         params=[Param("c", unit="r", choices=(0.5, 2.0))])

    assert "with a target index reaching 5;" in chosen.detail
    assert "with a target index with no declared highest;" in endless.detail
    assert _finding(_searching([Param("n", unit="objects", choices=(4, 8))], P("n"), 0),
                    "target-outside-array") == []
    (correlation,) = _finding(stereogram, "impossible-correlation")
    assert "whose correlation reaches 2;" in correlation.detail


def test_an_object_the_task_names_is_declared_when_the_set_size_can_reach_it():
    """Task 10's review, fix round 2: a set size with no highest was read as 0 objects, so an
    object the task names was undeclared; it can be any number, so every object index is one.
    One past the highest declared stays undeclared. **Only the objects the task names are
    listed**: every index up to the highest set size was, so a value sent past its range cost as
    many names as it was large, inside the widened check between two trials."""
    endless = [Param("n", unit="objects", low=2)]
    six = [Param("n", unit="objects", low=2, high=6)]
    twelve = [Param("n", unit="objects", low=2, high=12)]

    assert _finding(_searching(endless, P("n"), 0, "search.7"), "undeclared-window") == []
    assert _finding(_searching(six, P("n"), 0, "search.5"), "undeclared-window") == []
    (past,) = _finding(_searching(six, P("n"), 0, "search.6"), "undeclared-window")
    assert "'search.6'" in past.detail
    # Named exactly as a trial names its windows, or none: `search.05` is not `search.5`.
    assert len(_finding(_searching(six, P("n"), 0, "search.05"), "undeclared-window")) == 1
    assert _declared_window_names(_searching(twelve, P("n"), 0, "search.5")) == {
        "search.target", "search.distractor", "search.5"}


def _scoring_both(fix: Window, target: Window, params: list) -> Trial:
    """One state scoring a fixation window and a target window at once."""
    return Trial(
        start="wait",
        params=params,
        windows=[fix, target],
        states=[State("wait", enter=[Show(Stimulus("fix", at=(0.0, 0.0), looks=LIT))], go=[
            On(Entered("target"), Outcome.CORRECT),
            On(Entered("fix"), Outcome.WRONG_TARGET),
            On(After(1.0), Outcome.NO_RESPONSE),
        ])],
    )


def _overlap(trial) -> list:
    return [f for f in check(trial) if f.code == "overlapping-windows"]


def test_windows_whose_position_ranges_overlap_on_one_axis_are_found_between_the_corners():
    """Task 10's review, I2: the least distance between two windows was taken over the corners
    of their position ranges. A target 2° in radius over x 4-16° and y ±8° comes within 4° of a
    fixation window 3° in radius, at (4, 0) -- inside their summed 5° -- while its nearest corners
    are 8.9° away. Per axis, the distance between the ranges, 0 where they overlap: a warning at
    load (XC-352's A8)."""
    params = [Param("target_x", unit="deg", low=4.0, high=16.0),
              Param("target_y", unit="deg", low=-8.0, high=8.0)]
    trial = _scoring_both(Window("fix", at=(0.0, 0.0), radius=3.0, on="fix"),
                          Window("target", at=(P("target_x"), P("target_y")), radius=2.0, on="fix"),
                          params)

    (warning,) = _overlap(trial)

    assert warning.is_warning
    assert "which can come within 4.00° while their radii sum to 5.00°" in warning.detail
    assert _overlap(replace(trial, windows=[
        Window("fix", at=(0.0, 0.0), radius=1.0, on="fix"), trial.windows[1]])) == []


def test_a_window_setting_with_one_bound_is_read_without_the_other_never_as_zero():
    """Task 10's review, I2: a setting with one bound was left out of the ranges and read as 0,
    so it could never reach another window. A position's missing bound leaves that side
    unbounded, and a radius' missing highest leaves it any size, so an overlap cannot be ruled
    out and is warned of; a radius' missing lowest is 0."""
    target = Window("target", at=(P("target_x"), 0.0), radius=P("target_window"), on="fix")
    fix = Window("fix", at=(10.0, 0.0), radius=1.0, on="fix")

    def declared(*params):
        return _overlap(_scoring_both(fix, target, list(params)))

    # `target_x` up to 16° alone reaches 10°, where the fixation window is.
    (reaching,) = declared(Param("target_x", unit="deg", high=16.0),
                           Param("target_window", unit="deg", low=0.5, high=2.0))
    assert "which can come within 0.00°" in reaching.detail
    # A radius from 0.5° up, with no highest: any size, so any two windows can overlap.
    (any_size,) = declared(Param("target_x", unit="deg", low=-16.0, high=-4.0),
                           Param("target_window", unit="deg", low=0.5))
    assert "while a radius has no declared highest" in any_size.detail
    # Up to 2° alone: from 0, and 14° away it overlaps nothing.
    assert declared(Param("target_x", unit="deg", low=-16.0, high=-4.0),
                    Param("target_window", unit="deg", high=2.0)) == []


def test_an_appearance_parameter_is_checked_at_each_appearance_it_offers():
    """An appearance is a parameter too (S1a §4), and one of its choices may be an
    object ring. Check 8 looked only at a literal `Array`, so a ring offered as a choice
    was never measured."""
    looks = [Param("looks", unit="appearance", choices=(LIT, Array(radius=20.0)))]
    small = [Param("looks", unit="appearance", choices=(LIT, Array(radius=4.0)))]

    assert _off(_showing((0.0, 0.0), small, looks=P("looks"))) == []
    assert len(_off(_showing((0.0, 0.0), looks, looks=P("looks")))) == 1


def test_a_corrugation_is_checked_at_both_ends_of_its_amplitude():
    """The form was evaluated at each parameter's upper bound only, so an amplitude
    ranging over [-8, 0.1] was measured as 0.1. Its depth reaches 8."""
    lopsided = [Param("amp", unit="deg", low=-8.0, high=0.1)]
    patch = RDS(form=Corrugation(sf=0.5, amplitude=P("amp")))

    assert len(_off(_showing((10.0, 0.0), lopsided, looks=patch))) == 1


def test_a_corrugation_whose_amplitude_cannot_be_bounded_is_refused():
    """A form over a parameter the check cannot bound fell back to no depth at all."""
    chosen = [Param("amp", unit="deg", choices=(0.1, 8.0))]
    unranged = [Param("amp", unit="deg")]
    patch = RDS(form=Corrugation(sf=0.5, amplitude=P("amp")))

    assert len(_off(_showing((10.0, 0.0), chosen, looks=patch))) == 1
    (finding,) = _off(_showing((10.0, 0.0), unranged, looks=patch))
    assert "cannot be bounded" in finding.detail


def _updating(*updates, params=(), at=(0.0, 0.0)) -> Trial:
    """`s` shown at `at`, then each update in a state of its own, in order."""
    names = ["show"] + [f"update{i}" for i in range(len(updates))]
    nexts = names[1:] + [Outcome.CORRECT]
    return Trial(
        start="show",
        params=list(params),
        states=[
            State(
                name,
                enter=[Show(Stimulus("s", at=at, looks=LIT))] if name == "show" else [updates[i - 1]],
                go=[On(After(1.0), after)],
            )
            for i, (name, after) in enumerate(zip(names, nexts))
        ],
    )


def test_an_update_that_moves_a_stimulus_off_screen_is_refused():
    """XC-037: `Update(at=...)` escaped check 8, so a stimulus shown legally could be
    moved off the panel one state later and nothing said so."""
    assert _off(_updating(Update("s", at=(5.0, 0.0)))) == []
    (finding,) = _off(_updating(Update("s", at=(30.0, 0.0))))
    assert "'update0'" in finding.detail


def test_an_update_over_a_parameter_is_checked_across_its_range():
    ranged = [Param("x", unit="deg", low=-30.0, high=0.0)]

    assert len(_off(_updating(Update("s", at=(P("x"), 0.0)), params=ranged))) == 1


def test_an_update_that_adds_disparity_is_refused_when_it_takes_one_eye_off_screen():
    """XC-037's disparity half: the same 2 degrees of near disparity at 10 that a `Show`
    is refused for, arriving by `Update`."""
    assert len(_off(_updating(Update("s", disparity=-2.0), at=(10.0, 0.0)))) == 1


def test_an_update_that_turns_a_stimulus_into_a_wide_ring_is_refused():
    assert len(_off(_updating(Update("s", looks=Array(radius=20.0))))) == 1


def test_two_updates_that_are_each_safe_are_checked_together():
    """Moving to 10 is legal and so is 2 degrees of near disparity at the centre; after
    both, the left eye's image is past the mask. An update leaves every property it does not
    set as an earlier `Show` or `Update` left it, so each is checked against those."""
    move = Update("s", at=(10.0, 0.0))
    deepen = Update("s", disparity=-2.0)

    assert _off(_updating(move)) == []
    assert _off(_updating(deepen)) == []
    assert len(_off(_updating(move, deepen))) >= 1


# ---------------------------------------------------------------------------
# Which setup a task is written for (direct-view spec §3)
# ---------------------------------------------------------------------------


def _task(*enter, view="either", params=()) -> Trial:
    """One state that shows a plain disc, then does `enter`, then ends."""
    return Trial(
        start="show",
        view=view,
        params=list(params),
        states=[
            State(
                "show",
                enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=LIT)), *enter],
                go=[On(After(1.0), Outcome.CORRECT)],
            ),
        ],
    )


def test_a_task_is_either_until_it_says_otherwise():
    """The default is safe because check 8 runs against whichever setup the session
    chose -- once direct view part 2 passes the session's geometry; until then only
    the tests run it -- so an undeclared task in the stereoscope is held to the
    mask."""
    assert _task().view == "either"
    assert check(_task(), geometry=DIRECT) == []
    assert check(_task(), geometry=GEOMETRY) == []


def test_disparity_needs_a_task_that_declares_the_stereoscope():
    """"Two side-by-side images on an unmirrored screen are not a stimulus." Refused
    with or without a geometry: it is the task's content, not the session's."""
    shifted = Update("s", disparity=0.4)

    (finding,) = check(_task(shifted))
    assert finding.code == "needs-stereoscope"
    assert "gives 's' disparity" in finding.detail
    assert "view='either'" in finding.detail
    assert [f.code for f in check(_task(shifted, view="direct"))] == ["needs-stereoscope"]
    assert check(_task(shifted, view="stereoscope")) == []


def test_a_disparity_parameter_counts_when_its_range_can_leave_zero():
    """Over the declared range, as every range check here: a disparity an
    experimenter can dial in is disparity."""
    ranged = [Param("d", unit="deg", low=-0.5, high=0.5)]
    pinned = [Param("d", unit="deg", low=0.0, high=0.0)]

    assert [f.code for f in check(_task(Update("s", disparity=P("d")), params=ranged))] == [
        "needs-stereoscope"
    ]
    assert check(_task(Update("s", disparity=P("d")), params=pinned)) == []


def test_a_disparity_parameter_declared_by_choices_counts():
    """Review I1(a): a disparity parameter with no `low`/`high` -- declared by
    `choices` instead -- is not the `(0, 0)` `_widest` fell back to for an
    undeclared range (it is gone since Task 10's review, fix round 2). `taskd` would
    accept any listed choice, so the checker must
    count the non-zero ones as stereo content too."""
    choices = [Param("d", unit="deg", choices=(-0.4, 0.0, 0.4))]
    pinned = [Param("d", unit="deg", choices=(0.0,))]

    assert [f.code for f in check(_task(Update("s", disparity=P("d")), params=choices))] == [
        "needs-stereoscope"
    ]
    assert check(_task(Update("s", disparity=P("d")), params=pinned)) == []


def test_a_shown_stereogram_or_one_a_parameter_can_choose_needs_the_stereoscope():
    """A random-dot stereogram has no content but its disparity. One reachable only
    through a parameter's choices is as real as one written into a `Show`."""
    shown = _task(Show(Stimulus("rds", at=(0.0, 0.0), looks=RDS())))
    chosen = _task(params=[Param("looks", unit="appearance", choices=(RDS(),))])
    updated = _task(Update("s", looks=RDS()))

    for trial in (shown, chosen, updated):
        (finding,) = check(trial)
        assert finding.code == "needs-stereoscope"
        assert "random-dot stereogram" in finding.detail


def test_a_stereogram_inside_an_arrays_looks_or_among_needs_the_stereoscope():
    """Review I1(b): `_appearances` reports the `Array` itself, not the `RDS`
    nested in its `looks`/`among` -- so an array of stereograms in an "either" task
    must still be found, whichever slot carries the `RDS`."""
    as_looks = _task(Show(Stimulus("arr", at=(0.0, 0.0), looks=Array(looks=RDS(), among=LIT))))
    as_among = _task(Show(Stimulus("arr", at=(0.0, 0.0), looks=Array(looks=LIT, among=RDS()))))

    for trial in (as_looks, as_among):
        (finding,) = check(trial)
        assert finding.code == "needs-stereoscope"
        assert "random-dot stereogram" in finding.detail


def test_a_stimulus_shown_to_one_eye_needs_the_stereoscope():
    """Plan decision: an unmirrored screen shows both eyes one image, so a stimulus
    for one eye is the same impossibility as disparity -- by `Show` or by `Update`."""
    left = _task(Show(Stimulus("left", at=(2.0, 0.0), eye="left", looks=LIT)))
    right = _task(Update("s", eye="right"))

    assert [f.detail.split(",")[0] for f in check(left)] == [
        "state 'show' shows 'left' to the left eye only"
    ]
    assert [f.code for f in check(right)] == ["needs-stereoscope"]
    assert check(_task(Update("s", eye="both"))) == []


def test_a_task_written_for_one_setup_is_a_warning_in_the_other_naming_both():
    """Spec §3: "a stereoscope task in direct view, or a direct task in the stereoscope".
    **A warning, not a refusal, when it shows nothing that needs each eye its own image**
    (XC-352's A12; the PI, 2026-10-11): it runs, and the warning says what the other setup
    changes. The field check still holds it to the setup it runs in."""
    (in_direct,) = check(_task(view="stereoscope"), geometry=DIRECT)
    (in_stereoscope,) = check(_task(view="direct"), geometry=GEOMETRY)

    assert in_direct.code == in_stereoscope.code == "wrong-setup"
    for warning in (in_direct, in_stereoscope):
        assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "written for 'stereoscope'" in in_direct.detail
    assert "checked against 'direct'" in in_direct.detail
    assert "both eyes see the whole panel" in in_direct.detail
    assert "written for 'direct'" in in_stereoscope.detail
    assert "checked against 'stereoscope'" in in_stereoscope.detail
    assert "each eye sees its own half of the panel, inside the ±12° mask" in in_stereoscope.detail
    assert check(_task(view="direct"), geometry=DIRECT) == []
    assert check(_task(view="stereoscope"), geometry=GEOMETRY) == []


@pytest.mark.parametrize("shown", [
    Show(Stimulus("d", at=(1.0, 0.0), looks=LIT, disparity=0.2)),
    Show(Stimulus("l", at=(1.0, 0.0), looks=LIT, eye="left")),
    Show(Stimulus("p", at=(0.0, 0.0), looks=LIT, at_left=(1.0, 0.0), at_right=(-1.0, 0.0))),
    Update("s", at_left=(1.0, 0.0), at_right=(-1.0, 0.0)),
], ids=["a disparity", "one eye", "a position per eye", "a position per eye by an update"])
def test_a_stereoscope_task_that_shows_each_eye_its_own_image_is_refused_in_direct_view(shown):
    """What an unmirrored screen cannot show stays refused (XC-352's A12: "`needs-stereoscope`
    and the field check still refuse"): both eyes would see both images, so the record would
    not describe what was shown. A position per eye given by an `Update` too (Task 3's review,
    minor: without its case, `_per_eye_content`'s `Update` branch could go and the suite pass,
    and such a task would run in direct view with a warning, failing mid-trial)."""
    (refusal,) = check(_task(shown, view="stereoscope"), geometry=DIRECT)

    assert refusal.code == "wrong-setup" and refusal.blocking
    assert "which an unmirrored screen cannot show" in refusal.detail


def test_a_stereoscope_task_with_a_background_per_eye_is_refused_in_direct_view():
    """Engine spec §4.4: each eye's own background is the stereoscope's; an unmirrored screen
    has one."""
    task = replace(_task(view="stereoscope"), background_left=Gray(10.0), background_right=Gray(20.0))

    (refusal,) = [f for f in check(task, geometry=DIRECT) if f.code == "wrong-setup"]

    assert refusal.blocking and "it gives each eye its own background" in refusal.detail


def test_without_a_geometry_the_setup_is_unchecked():
    """`geometry=None` still means unchecked (S1 §9 check 8): a task is not wrong for
    being checked without a rig."""
    assert check(_task(view="stereoscope")) == []
    assert check(_task(view="direct")) == []


def test_a_view_that_is_no_setup_is_refused():
    """`view="stereo"` is not a declaration. Read as either setup it would be checked
    against the wrong one; read as neither it would pass everything."""
    (finding,) = check(_task(Update("s", disparity=0.4), view="stereo"), geometry=DIRECT)

    assert finding.code == "unknown-view"
    assert "'stereo'" in finding.detail


# ---------------------------------------------------------------------------
# Check 8 on extent, not just centre, reaching a housing (Task 3 review)
# ---------------------------------------------------------------------------


def test_an_arrays_ring_reaching_a_housing_is_refused_even_though_its_centre_is_legal():
    """Task 3 review: check 8 already refuses a stimulus whose *extent* reaches a
    housing in direct view -- not only one whose centre sits under it. An `Array`'s
    object ring makes the point without disparity, which would also trip the new
    needs-stereoscope finding in direct view."""
    centre = (-25.0, -16.0)
    assert DIRECT.can_show(*centre), "the centre alone is legal"
    assert check(_showing(centre), geometry=DIRECT) == []

    (finding,) = check(_showing(centre, looks=Array(radius=2.0, looks=LIT, among=LIT)), geometry=DIRECT)

    assert finding.code == "stimulus-off-screen"
    assert "direct field, less the light sensors' housings" in finding.detail
