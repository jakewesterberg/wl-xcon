"""Load-time checks over what is on the display.

Every earlier check inspects the transition graph, so the residual defect class was
"correct graph, wrong experiment" -- a task holding fixation on a point it had taken
down passed all ten. These close that class statically; `test_simulate` closes it
dynamically. Both, because a static check finds it without a subject and simulation
finds it without the author having coupled anything.
"""

import dataclasses

import pytest

from _rig import STEREOSCOPE
from wl_xcon import look
from wl_xcon.check import check
from wl_xcon.photometry import RMS, Gray, Michelson, Weber
from wl_xcon.task import (
    REMEMBERED,
    After,
    Annulus,
    Array,
    Disc,
    Entered,
    Gabor,
    Hide,
    Hold,
    On,
    Outcome,
    P,
    Param,
    Show,
    State,
    Stimulus,
    Trial,
    Update,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))


def codes(trial: Trial) -> set[str]:
    return {finding.code for finding in check(trial)}


def test_a_hold_on_a_stimulus_that_is_not_displayed_is_refused():
    """The bug the review found, as a load-time refusal."""
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[
            State(
                "await_fix",
                enter=[Show(FIX)],
                go=[
                    On(Entered("fix"), "hold_fix", do=[Hide("fix")]),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.3), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )
    assert "nothing-to-look-at" in codes(trial)


def test_a_stimulus_shown_in_an_earlier_state_satisfies_a_later_hold():
    """A `Show` persists, so the reference structure is legal -- which is the whole
    reason the semantics changed rather than the task."""
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[
            State(
                "await_fix",
                enter=[Show(FIX)],
                go=[
                    On(Entered("fix"), "hold_fix"),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.3), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )
    assert "nothing-to-look-at" not in codes(trial)


def test_a_stimulus_shown_on_only_one_path_in_is_refused():
    """Visible on *some* route into a state is not visible.

    A task where one branch shows the target and another does not is the kind of
    thing that works for a hundred trials and then scores a hold against a blank
    screen on whichever branch nobody tested.
    """
    trial = Trial(
        start="choose",
        windows=[Window("t", at=(8.0, 0.0), radius=2.0, on="target")],
        states=[
            State(
                "choose",
                go=[
                    On(
                        Entered("t"),
                        "verify",
                        do=[Show(Stimulus("target", at=(8.0, 0.0)))],
                    ),
                    On(After(1.0), "verify"),
                ],
            ),
            State(
                "verify",
                go=[
                    On(Hold("t", 0.2), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    assert "nothing-to-look-at" in codes(trial)


def test_a_remembered_window_needs_no_stimulus():
    trial = Trial(
        start="wait",
        windows=[Window("mem", at=(8.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State(
                "wait",
                go=[
                    On(Hold("mem", 0.2), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    assert "nothing-to-look-at" not in codes(trial)


def test_a_window_that_declares_no_coupling_is_refused():
    """Unset is not the same as `REMEMBERED`.

    If unset were allowed to mean "nothing there", the check above would be opt-in
    -- and the tasks most likely to skip it are the ones written fastest.
    """
    trial = Trial(
        start="wait",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State("wait", go=[On(After(1.0), Outcome.NO_FIXATION)]),
        ],
    )
    assert "uncoupled-window" in codes(trial)


def test_hiding_or_updating_a_stimulus_that_is_not_displayed_is_refused():
    trial = Trial(
        start="wait",
        windows=[],
        states=[
            State(
                "wait",
                enter=[Update("ghost", at=(1.0, 0.0))],
                go=[On(After(1.0), Outcome.ABORT, do=[Hide("phantom")])],
            ),
        ],
    )
    found = codes(trial)
    assert "absent-stimulus" in found


def test_an_update_that_changes_nothing_is_refused():
    trial = Trial(
        start="wait",
        windows=[],
        states=[
            State(
                "wait",
                enter=[Show(FIX), Update("fix")],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )
    assert "empty-update" in codes(trial)


GRAY_BG = Gray(20.0)


def _one(looks, *, params=(), **trial_fields) -> Trial:
    """One stimulus, shown and held a second."""
    return Trial(
        start="on",
        params=list(params),
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
        states=[
            State(
                "on",
                enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=looks))],
                go=[On(After(1.0), Outcome.ABORT)],
            )
        ],
        **trial_fields,
    )


def _refused(trial: Trial) -> set[str]:
    return {f.code for f in check(trial) if f.blocking}


@pytest.mark.parametrize("looks, background, code", [
    (Disc(contrast=0.5), GRAY_BG, "bare-contrast"),
    (Disc(), None, "unlit"),
    (Disc(contrast=Weber(0.5)), None, "weber-on-black"),
    (Disc(contrast=Michelson(0.5)), GRAY_BG, "contrast-convention"),
    (Disc(color=Gray(40.0), contrast=Weber(0.2)), GRAY_BG, "overspecified-color"),
    (Gabor(), GRAY_BG, "unlit"),
    (Gabor(contrast=Michelson(0.5)), None, "unlit"),
    (Gabor(contrast=Weber(0.5)), GRAY_BG, "contrast-convention"),
    (Gabor(contrast=RMS(0.2)), GRAY_BG, "contrast-convention"),
    (look.Look(shape=look.Circle(size=1.0), fill=look.Flat(color=Gray(10.0)),
               outline=look.Outline(width=0.1)), None, "unlit"),
])
def test_a_stimulus_without_a_light_the_drawer_can_honor_is_refused(looks, background, code):
    assert code in _refused(_one(looks, background=background))


@pytest.mark.parametrize("looks", [
    Disc(size=0.0, color=Gray(40.0)),
    look.Look(shape=look.Circle(size=-1.0), fill=look.Flat(color=Gray(40.0))),
    Annulus(inner=2.0, outer=1.0, color=Gray(40.0)),
    Gabor(contrast=Michelson(1.5)),
    Disc(contrast=Weber(-1.5)),
    look.Look(shape=look.Path(points=((0.0, 0.0),), width=0.1), fill=look.Flat(color=Gray(40.0))),
    look.Look(shape=look.RegularPolygon(sides=2), fill=look.Flat(color=Gray(40.0))),
    look.Look(shape=look.Vertices(points=((0.0, 0.0), (1.0, 0.0))), fill=look.Flat(color=Gray(40.0))),
    look.Look(fill=look.Flat(color=Gray(40.0)), edge=look.GaussianEdge(applies="blend")),
])
def test_a_degenerate_block_is_refused_at_load(looks):
    assert "bad-block" in _refused(_one(looks, background=GRAY_BG))


def test_a_contrast_parameter_is_bare_unless_its_choices_name_their_convention():
    bare = [Param("c", unit="fraction", low=0.0, high=1.0)]
    named = [Param("c", unit="contrast", choices=(Weber(0.2), Weber(0.4)))]
    assert "bare-contrast" in _refused(_one(Disc(contrast=P("c")), params=bare, background=GRAY_BG))
    assert "bare-contrast" not in _refused(_one(Disc(contrast=P("c")), params=named, background=GRAY_BG))
    assert "bare-contrast" not in _refused(
        _one(Disc(contrast=Weber(P("c"))), params=bare, background=GRAY_BG))


def test_weber_against_a_declared_background_is_accepted():
    assert _refused(_one(Disc(contrast=Weber(0.5)), background=GRAY_BG)) == set()


def test_weber_is_on_black_if_either_eye_s_background_is():
    trial = _one(Disc(contrast=Weber(0.5)), view="stereoscope", background_left=GRAY_BG)
    assert "weber-on-black" in _refused(trial)


def test_a_grating_with_a_declared_mean_on_another_background_is_warned_not_refused():
    grating = look.Look(shape=look.Circle(size=4.0),
                        fill=look.SineGrating(contrast=Michelson(0.5), mean=Gray(30.0)))
    findings = check(_one(grating, background=GRAY_BG))
    assert [f.code for f in findings] == ["luminance-step"]
    assert not findings[0].blocking


def test_an_array_s_items_must_be_lit_too():
    assert "unlit" in _refused(_one(Array(looks=Disc(color=Gray(40.0)))))


def test_a_degenerate_block_inside_an_array_member_is_reported_once():
    items = Array(looks=Disc(size=0.0, color=Gray(40.0)), among=Disc(color=Gray(40.0)))
    findings = [f.code for f in check(_one(items, background=GRAY_BG)) if f.blocking]
    assert findings.count("bad-block") == 1


LIT = Disc(color=Gray(40.0))


def _placed(*, view="stereoscope", looks=LIT, background=None, at=(0.0, 0.0), params=(),
            **fields) -> Trial:
    return Trial(
        start="on",
        view=view,
        background=background,
        params=list(params),
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
        states=[
            State(
                "on",
                enter=[Show(Stimulus("s", at=at, looks=looks, **fields))],
                go=[On(After(1.0), Outcome.ABORT)],
            )
        ],
    )


@pytest.mark.parametrize("fields, code", [
    ({"opacity": 1.5}, "bad-placement"),
    ({"opacity": -0.1}, "bad-placement"),
    ({"layer": 1.5}, "bad-placement"),
    ({"combine": "blend"}, "bad-placement"),
    ({"combine": "multiply"}, "multiply-needs-modulation"),
    ({"at_left": (1.0, 0.0)}, "per-eye-misused"),
    ({"at_left": (1.0, 0.0), "at_right": (-1.0, 0.0), "disparity": 0.1}, "per-eye-misused"),
])
def test_a_placement_the_drawer_cannot_honor_is_refused(fields, code):
    assert code in _refused(_placed(**fields))


@pytest.mark.parametrize("view", ["direct", "either"])
def test_per_eye_positions_need_a_task_written_for_the_stereoscope(view):
    assert "per-eye-misused" in _refused(_placed(view=view, at_left=(1.0, 0.0), at_right=(-1.0, 0.0)))


def test_what_the_drawer_can_honor_is_accepted():
    assert _refused(_placed(at_left=(1.0, 0.0), at_right=(-1.0, 0.0), layer=2, opacity=0.5)) == set()
    gain = _placed(looks=Disc(contrast=Weber(-0.5)), background=GRAY_BG, combine="multiply")
    assert _refused(gain) == set()


def test_an_update_cannot_mix_per_eye_positions_with_disparity():
    def updating(show, update):
        return Trial(
            start="a", view="stereoscope",
            states=[
                State("a", enter=[Show(show)], go=[On(After(0.5), "b")]),
                State("b", enter=[update], go=[On(After(0.5), Outcome.ABORT)]),
            ],
        )
    per_eye = Stimulus("s", at=(0.0, 0.0), looks=LIT, at_left=(1.0, 0.0), at_right=(-1.0, 0.0))
    deep = Stimulus("s", at=(0.0, 0.0), looks=LIT, disparity=0.2)
    assert "per-eye-misused" in _refused(updating(per_eye, Update("s", disparity=0.3)))
    assert "per-eye-misused" in _refused(
        updating(deep, Update("s", at_left=(1.0, 0.0), at_right=(0.0, 0.0))))
    assert "per-eye-misused" in _refused(updating(per_eye, Update("s", at_left=(2.0, 0.0))))


def test_an_unknown_periphery_and_a_per_eye_background_off_the_stereoscope_are_refused():
    assert "bad-periphery" in _refused(_one(LIT, periphery="curved"))
    assert "per-eye-background" in _refused(_one(LIT, view="direct", background_left=GRAY_BG))


def test_a_background_s_parameter_must_be_declared():
    assert "undeclared-parameter" in _refused(_one(LIT, background=Gray(P("bg"))))


def _off(trial, geometry=STEREOSCOPE) -> list:
    return [f for f in check(trial, geometry=geometry) if f.code == "stimulus-off-screen"]


def test_the_vergence_offset_can_carry_one_eye_s_image_behind_the_mask():
    # Straight ahead at 11°, the left eye's image is at 11 + 1.45 = 12.45°: behind ±12°.
    (finding,) = _off(_placed(at=(11.0, 0.0)))
    assert "vergence" in finding.detail
    assert _off(_placed(at=(10.5, 0.0))) == []


def test_only_the_eyes_that_see_a_stimulus_are_measured():
    # The right eye's image of 11° is at 11 − 1.45 = 9.55°.
    assert _off(_placed(at=(11.0, 0.0), eye="right")) == []


def test_per_eye_positions_are_measured_as_given():
    # Already each eye's own direction: no vergence offset is added to them.
    assert _off(_placed(at_left=(11.9, 0.0), at_right=(-11.9, 0.0))) == []
    assert len(_off(_placed(at_left=(12.5, 0.0), at_right=(0.0, 0.0)))) == 1


def test_an_update_that_widens_the_eye_is_measured_for_the_eye_it_adds():
    # Shown to the right eye alone, 11° is fine (9.55°); both eyes would put the left at 12.45°.
    def widening(*enter, show_eye="right"):
        return Trial(
            start="a", view="stereoscope",
            states=[
                State("a", enter=[Show(Stimulus("s", at=(11.0, 0.0), looks=LIT, eye=show_eye))],
                      go=[On(After(0.5), "b")]),
                State("b", enter=list(enter), go=[On(After(0.5), Outcome.ABORT)]),
            ],
        )
    assert _off(widening(Update("s", layer=1))) == []
    assert len(_off(widening(Update("s", eye="both")))) == 1


def test_a_second_show_with_a_wider_eye_is_measured_with_an_update_of_the_name():
    trial = Trial(
        start="a", view="stereoscope",
        states=[
            State("a", enter=[Show(Stimulus("s", at=(11.0, 0.0), looks=LIT, eye="right"))],
                  go=[On(After(0.5), "b")]),
            State("b", enter=[Show(Stimulus("s", at=(11.0, 0.0), looks=LIT, eye="both")),
                              Update("s", layer=1)],
                  go=[On(After(0.5), Outcome.ABORT)]),
        ],
    )
    findings = _off(trial)
    assert len(findings) >= 1 and any("updates" in f.detail for f in findings)


def _two_updates(show, first, second) -> Trial:
    return Trial(
        start="a", view="stereoscope",
        states=[
            State("a", enter=[Show(show)], go=[On(After(0.5), "b")]),
            State("b", enter=[first], go=[On(After(0.5), "c")]),
            State("c", enter=[second], go=[On(After(0.5), Outcome.ABORT)]),
        ],
    )


def test_an_update_after_an_update_is_checked_for_per_eye_positions_and_disparity():
    plain = Stimulus("s", at=(0.0, 0.0), looks=LIT)
    trial = _two_updates(plain, Update("s", disparity=0.3),
                         Update("s", at_left=(1.0, 0.0), at_right=(-1.0, 0.0)))
    assert "per-eye-misused" in _refused(trial)


def test_an_update_after_an_update_is_checked_for_multiply_on_an_absolute_light():
    gain = Stimulus("s", at=(0.0, 0.0), looks=Disc(contrast=Weber(-0.5)), combine="multiply")
    trial = _two_updates(gain, Update("s", layer=1), Update("s", looks=Disc(color=Gray(40.0))))
    trial = dataclasses.replace(trial, background=GRAY_BG)
    assert "multiply-needs-modulation" in _refused(trial)


# --- What a parameter can make of a stimulus (engine A1, the final review) --------
#
# The lab writes live values as parameters, so a check that reads only literals passes
# the tasks it most needs to see. Each rule a literal is held to holds at every value a
# parameter can take: each choice, or both ends of its range; one it cannot read or
# bound is refused, as check 8 fails closed.

WEBER = Disc(contrast=Weber(-0.5))


def _choices(*values) -> list[Param]:
    return [Param("x", unit="value", choices=values)]


def _multiplying(looks, params=()) -> Trial:
    return _placed(looks=looks, background=GRAY_BG, combine="multiply", params=params)


def test_multiply_reads_each_item_of_an_array():
    assert "multiply-needs-modulation" in _refused(_multiplying(Array(looks=LIT, among=LIT)))
    assert "multiply-needs-modulation" in _refused(_multiplying(Array(looks=WEBER, among=LIT)))
    assert _refused(_multiplying(Array(looks=WEBER, among=WEBER))) == set()


def test_multiply_reads_each_choice_of_an_appearance_parameter():
    assert "multiply-needs-modulation" in _refused(_multiplying(P("x"), _choices(WEBER, LIT)))
    assert _refused(_multiplying(P("x"), _choices(WEBER, Disc(contrast=Weber(0.5))))) == set()


def test_multiply_refuses_an_appearance_parameter_it_cannot_read():
    found = [f.detail for f in check(_multiplying(P("x"), [Param("x", unit="appearance")]))
             if f.code == "multiply-needs-modulation"]
    assert len(found) == 1 and "cannot be read" in found[0]


def test_an_update_that_can_leave_an_array_of_absolute_lights_multiplying_is_refused():
    gain = Stimulus("s", at=(0.0, 0.0), looks=WEBER, combine="multiply")
    trial = _two_updates(gain, Update("s", layer=1), Update("s", looks=Array(looks=LIT, among=LIT)))
    assert "multiply-needs-modulation" in _refused(dataclasses.replace(trial, background=GRAY_BG))


@pytest.mark.parametrize("looks, choices, background, code", [
    (Disc(contrast=P("x")), (Michelson(0.5),), GRAY_BG, "contrast-convention"),
    (Disc(contrast=P("x")), (Weber(0.5),), None, "weber-on-black"),
    (Gabor(contrast=P("x")), (RMS(0.2),), GRAY_BG, "contrast-convention"),
    (Gabor(contrast=P("x")), (Michelson(1.5),), GRAY_BG, "bad-block"),
    (Disc(color=P("x")), (Gray(40.0), None), GRAY_BG, "unlit"),
    (Disc(color=P("x")), (Gray(-5.0),), GRAY_BG, "bad-block"),
    (Disc(color=P("x"), contrast=Weber(0.2)), (Gray(40.0),), GRAY_BG, "overspecified-color"),
    (look.Look(fill=look.SineGrating(contrast=Michelson(0.5), mean=P("x"))), (Gray(20.0), None),
     None, "unlit"),
    (look.Look(fill=look.Flat(color=Gray(10.0)), outline=look.Outline(color=P("x"))),
     (Gray(10.0), None), GRAY_BG, "unlit"),
])
def test_a_light_written_as_a_parameter_is_held_to_each_choice(looks, choices, background, code):
    assert code in _refused(_one(looks, params=_choices(*choices), background=background))


@pytest.mark.parametrize("looks, choices", [
    (Disc(contrast=P("x")), (Weber(0.2), Weber(-0.4))),
    (Gabor(contrast=P("x")), (Michelson(0.2), Michelson(1.0))),
    (Disc(color=P("x")), (Gray(10.0), Gray(40.0))),
    (look.Look(fill=look.Flat(color=Gray(10.0)), outline=look.Outline(color=P("x"))), (Gray(40.0),)),
])
def test_a_light_parameter_whose_every_choice_is_sound_is_accepted(looks, choices):
    assert _refused(_one(looks, params=_choices(*choices), background=GRAY_BG)) == set()


@pytest.mark.parametrize("looks, background", [
    (Disc(color=P("x")), GRAY_BG),
    (look.Look(fill=look.Flat(color=Gray(10.0)), outline=look.Outline(color=P("x"))), GRAY_BG),
    (LIT, P("x")),
])
def test_a_color_parameter_that_offers_no_colors_cannot_be_read(looks, background):
    luminance = [Param("x", unit="cd/m2", low=0.0, high=100.0)]
    found = [(f.code, f.detail) for f in check(_one(looks, params=luminance, background=background))
             if f.blocking]
    assert [code for code, _ in found] == ["bad-block"] and "cannot be read" in found[0][1]


@pytest.mark.parametrize("looks, param", [
    (Disc(size=P("x"), color=Gray(40.0)), Param("x", unit="deg", low=-1.0, high=1.0)),
    (Disc(size=P("x"), color=Gray(40.0)), Param("x", unit="deg", choices=(1.0, 0.0))),
    (look.Look(shape=look.Ring(inner=P("x"), outer=2.0), fill=look.Flat(color=Gray(40.0))),
     Param("x", unit="deg", low=0.5, high=3.0)),
    (look.Look(shape=look.RegularPolygon(sides=P("x")), fill=look.Flat(color=Gray(40.0))),
     Param("x", unit="sides", choices=(2, 3))),
    (Gabor(contrast=Michelson(P("x"))), Param("x", unit="fraction", low=0.0, high=3.0)),
    (Disc(contrast=Weber(P("x"))), Param("x", unit="fraction", low=-3.0, high=1.0)),
    (Disc(color=Gray(P("x"))), Param("x", unit="cd/m2", low=-50.0, high=100.0)),
])
def test_a_degenerate_value_a_parameter_can_reach_is_refused_at_load(looks, param):
    assert "bad-block" in _refused(_one(looks, params=[param], background=GRAY_BG))


@pytest.mark.parametrize("looks, param", [
    (Disc(size=P("x"), color=Gray(40.0)), Param("x", unit="deg")),
    (Disc(size=P("x"), color=Gray(40.0)), Param("x", unit="deg", low=0.5)),
    (Disc(color=Gray(P("x"))), Param("x", unit="cd/m2")),
    (Disc(contrast=Weber(P("x"))), Param("x", unit="fraction", high=1.0)),
])
def test_a_parameter_that_cannot_be_bounded_is_refused_where_a_literal_is_checked(looks, param):
    found = [(f.code, f.detail) for f in check(_one(looks, params=[param], background=GRAY_BG))
             if f.blocking]
    assert [code for code, _ in found] == ["bad-block"] and "cannot be bounded" in found[0][1]


def test_a_parameter_whose_every_value_is_sound_is_accepted():
    params = [Param("s", unit="deg", low=0.1, high=2.0), Param("c", unit="fraction", low=-1.0, high=1.0),
              Param("m", unit="fraction", choices=(0.0, 1.0)), Param("L", unit="cd/m2", low=0.0, high=100.0)]
    looks = Array(looks=Disc(size=P("s"), contrast=Weber(P("c"))),
                  among=Gabor(sigma=P("s"), contrast=Michelson(P("m"))))
    # A background that can reach 0 cd/m² can be black, for each item.
    assert _refused(_one(looks, params=params, background=Gray(P("L")))) == {"weber-on-black", "unlit"}
    assert _refused(_one(looks, params=params, background=GRAY_BG)) == set()


def test_negative_light_is_refused_in_a_stimulus_and_in_a_background():
    assert "bad-block" in _refused(_one(Disc(color=Gray(-5.0)), background=GRAY_BG))
    assert "bad-block" in _refused(_one(LIT, background=Gray(-5.0)))
    reaches = [Param("bg", unit="cd/m2", low=-5.0, high=40.0)]
    assert "bad-block" in _refused(_one(LIT, params=reaches, background=Gray(P("bg"))))
    assert "bad-block" in _refused(_one(LIT, params=_choices(Gray(-5.0), GRAY_BG), background=P("x")))


def test_a_background_that_a_parameter_can_make_black_is_black_for_weber():
    weber = Disc(contrast=Weber(0.5))
    reaches = [Param("bg", unit="cd/m2", low=0.0, high=40.0)]
    lit = [Param("bg", unit="cd/m2", low=10.0, high=40.0)]
    assert "weber-on-black" in _refused(_one(weber, params=reaches, background=Gray(P("bg"))))
    assert _refused(_one(weber, params=lit, background=Gray(P("bg")))) == set()
    assert "weber-on-black" in _refused(_one(weber, params=_choices(GRAY_BG, None), background=P("x")))
    assert _refused(_one(weber, params=_choices(GRAY_BG, Gray(10.0)), background=P("x"))) == set()
    unbounded = [Param("bg", unit="cd/m2", low=10.0)]  # can be anything below: black, failing closed
    assert "weber-on-black" in _refused(_one(weber, params=unbounded, background=Gray(P("bg"))))


@pytest.mark.parametrize("param", [
    Param("o", unit="fraction", low=0.0, high=3.0),
    Param("o", unit="fraction", choices=(0.5, -0.1)),
    Param("o", unit="fraction"),
])
def test_an_opacity_a_parameter_can_take_outside_0_1_is_refused(param):
    assert "bad-placement" in _refused(_placed(opacity=P("o"), params=[param]))
    trial = _two_updates(Stimulus("s", at=(0.0, 0.0), looks=LIT), Update("s", layer=1),
                         Update("s", opacity=P("o")))
    assert "bad-placement" in _refused(dataclasses.replace(trial, params=[param]))


def test_an_opacity_parameter_inside_0_1_is_accepted():
    assert _refused(_placed(opacity=P("o"), params=[Param("o", unit="fraction", low=0.0, high=1.0)])) == set()


def test_a_fault_a_parameter_s_choices_repeat_is_reported_once():
    pattern = _choices(Michelson(0.3), Michelson(1.5))
    twice = Array(looks=Gabor(contrast=P("x")), among=Gabor(contrast=P("x")))
    assert [f.code for f in check(_one(twice, params=pattern, background=GRAY_BG))].count("bad-block") == 1
    flat = [f.code for f in check(_one(Disc(contrast=P("x")), params=pattern, background=GRAY_BG))]
    assert flat.count("contrast-convention") == 1


def test_an_undeclared_light_parameter_cannot_be_read():
    assert {"undeclared-parameter", "bad-block"} <= _refused(_one(Disc(color=P("col")), background=GRAY_BG))


def _drifting(*, tf=2.0, direction=None, orientation=0.0):
    return look.Look(shape=look.Circle(size=4.0), orientation=orientation,
                     fill=look.SineGrating(tf=tf, direction=direction, contrast=Michelson(0.5)))


def _blocks(trial: Trial) -> list[str]:
    return [f.detail for f in check(trial) if f.blocking and f.code == "bad-block"]


@pytest.mark.parametrize("grating, params", [
    (_drifting(direction=45.0), ()),                            # not across the bars
    (_drifting(tf=-1.0), ()),                                   # a speed is not negative
    (_drifting(tf=P("tf")), [Param("tf", unit="Hz", low=-1.0, high=4.0)]),
    (_drifting(direction=P("d")), [Param("d", unit="deg", low=0.0, high=360.0)]),
    (_drifting(direction=90.0, orientation=P("o")), [Param("o", unit="deg", low=0.0, high=180.0)]),
    (_drifting(direction=P("d")), [Param("d", unit="deg", choices=(90.0, 180.0))]),
    (_drifting(direction=90.0, orientation=P("o")), [Param("o", unit="deg", choices=(0.0, 45.0))]),
])
def test_a_drift_not_across_the_bars_is_refused_at_load(grating, params):
    assert _blocks(_one(grating, params=params, background=GRAY_BG))


def test_a_drift_across_the_bars_is_accepted():
    both = [Param("d", unit="deg", choices=(90.0, 270.0))]
    assert _refused(_one(_drifting(direction=P("d")), params=both, background=GRAY_BG)) == set()
    ranged = [Param("o", unit="deg", low=0.0, high=180.0)]
    assert _refused(_one(_drifting(orientation=P("o")), params=ranged, background=GRAY_BG)) == set()
    assert _refused(_one(_drifting(direction=120.0, orientation=30.0), background=GRAY_BG)) == set()


def test_an_unmodulated_message_names_the_field_it_could_not_read():
    flat = [Param("c", unit="value", low=0.0, high=1.0)]
    for looks, field in ((Disc(color=P("c")), "color"), (Disc(contrast=P("c")), "contrast"),
                         (P("c"), "appearance")):
        trial = _multiplying(looks, params=flat)
        detail = " ".join(f.detail for f in check(trial) if f.blocking)
        assert f"its {field} is parameter 'c'" in detail, (field, detail)


def test_a_background_the_range_of_a_parameter_reaches_black_says_to_raise_the_range():
    reaches = [Param("bg", unit="cd/m2", low=0.0, high=40.0)]
    weber = _one(Disc(contrast=Weber(0.5)), params=reaches, background=Gray(P("bg")))
    grating = _one(_drifting(), params=reaches, background=Gray(P("bg")))
    for trial in (weber, grating):
        said = " ".join(f.detail for f in check(trial) if f.blocking)
        assert "raise the low end" in said and "'bg'" in said
        assert "declare the" not in said
    for trial in (_one(Disc(contrast=Weber(0.5))), _one(_drifting())):
        said = " ".join(f.detail for f in check(trial) if f.blocking)
        assert "declare the" in said and "raise the low end" not in said


def _fill_choices(*fills):
    return [Param("f", unit="fill", choices=fills)]


def _bad_fill():
    return look.SineGrating(direction=45.0, contrast=Michelson(0.5))


def _good_fill():
    return look.SineGrating(direction=90.0, contrast=Michelson(0.5))


def test_a_parameter_fill_is_held_to_the_drift_rule_at_each_choice():
    shape = look.Circle(size=4.0)
    params = _fill_choices(_good_fill(), _bad_fill())
    direct = look.Look(shape=shape, fill=P("f"), orientation=0.0)
    assert _blocks(_one(direct, params=params, background=GRAY_BG))
    items = Array(looks=direct, among=direct)
    assert _blocks(_one(items, params=params, background=GRAY_BG))
    fine = _fill_choices(_good_fill(), look.SineGrating(direction=270.0, contrast=Michelson(0.5)))
    assert _refused(_one(direct, params=fine, background=GRAY_BG)) == set()
    assert _refused(_one(items, params=fine, background=GRAY_BG)) == set()
