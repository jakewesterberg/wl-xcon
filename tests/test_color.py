"""Colour, in a space the display cannot silently reinterpret.

RGB is a set of instructions to a particular monitor, not a description of a light,
so "red" in a task file means a different stimulus on every panel and nothing at all
in a methods section. The flagship pop-out paradigm -- a red target among green
distractors, isoluminant -- was unwritable in this vocabulary until now, and
*isoluminant* is the word that makes a measurement mandatory: it is a claim about
photometry, and a claim nobody measured is a claim that is usually false.
"""

from dataclasses import replace

import pytest

from _calibrations import LINEAR
from wl_xcon.check import check
from wl_xcon.photometry import D65, DKL, RMS, Calibration, Gray, Michelson, Weber, to_xyz, xyY
from wl_xcon.task import (
    REMEMBERED,
    After,
    Disc,
    On,
    Outcome,
    P,
    Param,
    Show,
    State,
    Stimulus,
    Trial,
    Window,
)

# A plausible sRGB-like panel, as if measured. Numbers here are illustrative and
# are not a claim about any panel we own -- a real one comes from a photometer and
# is committed under docs/measurements/.
PANEL = Calibration(
    red=xyY(0.640, 0.330, 45.0),
    green=xyY(0.300, 0.600, 145.0),
    blue=xyY(0.150, 0.060, 15.0),
    background=xyY(0.3127, 0.3290, 50.0),
    transfer=(LINEAR,) * 3,
    observer="macaque V(lambda), Sidley & Sperling 1967",
    measured_on="2026-08-31",
)


def a_task(looks) -> Trial:
    return Trial(
        start="on",
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
        states=[
            State(
                "on",
                enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=looks))],
                go=[On(After(1.0), Outcome.ABORT)],
            ),
        ],
    )


def codes(trial, calibration=PANEL) -> set[str]:
    return {f.code for f in check(trial, calibration=calibration)}


def test_a_colour_the_panel_cannot_produce_is_refused():
    """Outside the gamut is not a rendering artifact, it is a different stimulus.

    A monitor asked for a colour it cannot make clips, silently, and the clipped
    colour is neither the requested chromaticity nor the requested luminance -- so
    an isoluminant pair stops being isoluminant and the experiment's control
    condition quietly becomes a luminance manipulation.
    """
    # A monochromatic-locus red, well outside any three-primary display.
    assert "unrealizable-color" in codes(a_task(Disc(color=xyY(0.72, 0.28, 40.0))))


def test_a_colour_inside_the_gamut_is_accepted():
    assert "unrealizable-color" not in codes(a_task(Disc(color=xyY(0.500, 0.400, 30.0))))


def test_a_luminance_the_panel_cannot_reach_is_refused():
    """Inside the gamut in chromaticity and still impossible in brightness."""
    assert "unrealizable-color" in codes(a_task(Disc(color=xyY(0.3127, 0.3290, 900.0))))


def test_colour_without_a_calibration_is_refused():
    """No photometer, no colour.

    The alternative is a task that runs, looks convincing, and reports a colour
    nobody measured -- which is worse than one that will not load, because it
    reaches a methods section.
    """
    assert "uncalibrated-color" in codes(
        a_task(Disc(color=xyY(0.500, 0.400, 30.0))), calibration=None
    )


def test_an_achromatic_task_needs_no_calibration():
    # Absolute luminance on the default calibration is a session warning (engine build B, XC-243).
    assert codes(a_task(Disc(size=1.0, color=Gray(40.0))), calibration=None) == set()


def test_isoluminance_is_a_declared_measurement_not_a_default():
    """`DKL(lum=0)` is isoluminant *by construction*, against a stated observer.

    Construction alone is not enough: the cone contrasts depend on whose luminous
    efficiency the display was measured against, and a macaque's is not a human's.
    A calibration that does not say refuses the colour rather than letting the task
    inherit a silent assumption about the species in the chair.
    """
    unstated = Calibration(
        red=PANEL.red,
        green=PANEL.green,
        blue=PANEL.blue,
        background=PANEL.background,
        transfer=(LINEAR,) * 3,
        observer="",
        measured_on="2026-08-31",
    )
    isoluminant = Disc(color=DKL(lum=0.0, l_m=0.08))
    assert "unstated-observer" in codes(a_task(isoluminant), calibration=unstated)
    assert "unstated-observer" not in codes(a_task(isoluminant), calibration=PANEL)


def test_a_cone_contrast_beyond_the_measured_maximum_is_refused():
    """The panel's reachable cone contrast is a measured number, not an aspiration."""
    assert "unrealizable-color" in codes(a_task(Disc(color=DKL(l_m=0.95))))


def test_pop_out_is_expressible_as_one_parameter():
    """The paradigm this gap blocked.

    Target and distractors differ in one feature, and which feature is a value --
    so a colour pop-out and a shape pop-out are the same task with a different
    parameter, which is exactly what the declarative model is for.
    """
    red = Disc(size=1.0, color=DKL(lum=0.0, l_m=0.08))
    green = Disc(size=1.0, color=DKL(lum=0.0, l_m=-0.08))
    param = Param("target_looks", unit="appearance", choices=(red, green))
    assert param.choices[0].color.lum == 0.0
    assert param.choices[0].color != param.choices[1].color


def test_an_absolute_colour_cannot_also_carry_a_contrast():
    """`xyY` names a light; `contrast` scales a modulation. Both at once means two
    different things claim to set the same physical quantity, and which one wins is
    the sort of thing nobody discovers until the figures disagree."""
    assert "overspecified-color" in codes(
        a_task(Disc(color=xyY(0.500, 0.400, 30.0), contrast=Weber(0.5)))
    )



def test_gray_is_d65_white_at_its_luminance():
    X, Y, Z = to_xyz(Gray(40.0))
    assert Y == 40.0
    assert (round(X / (X + Y + Z), 4), round(Y / (X + Y + Z), 4)) == D65


def test_an_xyy_color_converts_to_xyz_with_its_luminance():
    X, Y, Z = to_xyz(xyY(0.64, 0.33, 21.26))
    assert Y == 21.26
    assert X == pytest.approx(0.64 / 0.33 * 21.26)
    assert Z == pytest.approx((1 - 0.64 - 0.33) / 0.33 * 21.26)


def test_a_color_relative_to_the_background_is_no_light_by_itself():
    with pytest.raises(TypeError, match="relative to the background"):
        to_xyz(DKL(lum=0.1))


def test_each_contrast_names_its_convention():
    assert [type(c).__name__ for c in (Weber(0.3), Michelson(0.5), RMS(0.2))] == [
        "Weber", "Michelson", "RMS"]
    assert Weber(0.3) != Michelson(0.3)


def test_an_absolute_luminance_the_panel_cannot_reach_is_refused():
    assert "unrealizable-color" in codes(a_task(Disc(color=Gray(900.0))))


def test_a_background_is_a_color_like_any_other():
    trial = replace(a_task(Disc(color=Gray(10.0))), background=xyY(0.72, 0.28, 40.0))
    assert "unrealizable-color" in codes(trial)


def test_a_look_s_colors_are_checked_too():
    from wl_xcon import look
    looks = look.Look(fill=look.Flat(color=Gray(10.0)),
                      outline=look.Outline(width=0.1, color=xyY(0.72, 0.28, 40.0)))
    assert "unrealizable-color" in codes(a_task(looks))


def test_a_luminance_parameter_is_checked_at_both_ends_of_its_range():
    def ranging(low, high):
        return replace(a_task(Disc(color=Gray(P("lum")))),
                       params=[Param("lum", unit="cd/m2", low=low, high=high)])
    assert "unrealizable-color" not in codes(ranging(0.0, 100.0))
    assert "unrealizable-color" in codes(ranging(0.0, 900.0))
    assert "unrealizable-color" in codes(ranging(-10.0, 50.0))


def test_a_color_parameter_s_choices_are_each_checked_against_the_panel():
    def offering(*choices):
        return replace(a_task(Disc(color=P("c"))), params=[Param("c", unit="color", choices=choices)])
    assert "unrealizable-color" in codes(offering(Gray(10.0), xyY(0.72, 0.28, 40.0)))
    assert "uncalibrated-color" in codes(offering(xyY(0.500, 0.400, 30.0)), calibration=None)
    assert codes(offering(Gray(10.0), xyY(0.500, 0.400, 30.0))) == set()


def test_a_luminance_parameter_that_cannot_be_bounded_is_refused_not_raised():
    trial = replace(a_task(Disc(color=Gray(P("lum")))), params=[Param("lum", unit="cd/m2")])
    assert "bad-block" in codes(trial)


def test_a_number_where_a_color_belongs_is_refused_not_passed_to_the_drawer():
    """With a calibration this loaded, and `resolve` then called it a cone contrast for a
    later build to draw (XC-264)."""
    assert "bad-block" in codes(a_task(Disc(color=10.0)))
    offering = replace(a_task(Disc(color=P("c"))),
                       params=[Param("c", unit="cd/m2", choices=(10.0, 20.0))])
    assert "bad-block" in codes(offering)


def test_a_color_written_as_a_parameter_still_loads():
    ranged = replace(a_task(Disc(color=Gray(P("lum")))),
                     params=[Param("lum", unit="cd/m2", low=0.0, high=100.0)])
    offered = replace(a_task(Disc(color=P("c"))),
                      params=[Param("c", unit="color", choices=(Gray(10.0), xyY(0.5, 0.4, 30.0)))])
    assert codes(ranged) == set() and codes(offered) == set()


def test_a_luminance_still_a_parameter_must_be_bound_before_it_converts():
    with pytest.raises(TypeError, match="bind"):
        to_xyz(Gray(P("x")))


# --- Colors with parameters inside, under a calibration (XC-261) ----------------------


def _direct(color, params):
    return replace(a_task(Disc(color=color)), params=list(params))


def _chosen(color, params):
    return replace(a_task(Disc(color=P("c"))),
                   params=[*params, Param("c", unit="color", choices=(color,))])


@pytest.mark.parametrize("written", [_direct, _chosen])
def test_an_xyy_whose_luminance_is_a_parameter_is_checked_at_each_value_it_can_take(written):
    """Under a calibration this raised TypeError, so `check()` neither loaded the task nor
    refused it (XC-261). It is checked as `Gray(P(...))` is: at both ends of the range, or
    at each choice; written directly, or as a color parameter's choice."""
    red = xyY(0.64, 0.33, P("Y"))
    assert codes(written(red, [Param("Y", unit="cd/m2", low=0.0, high=10.0)])) == set()
    assert codes(written(red, [Param("Y", unit="cd/m2", low=0.0, high=900.0)])) == {
        "unrealizable-color"}
    assert codes(written(red, [Param("Y", unit="cd/m2", choices=(10.0, 900.0))])) == {
        "unrealizable-color"}
    # With no calibration it is unmeasured once, as written, as a literal is.
    unmeasured = check(written(red, [Param("Y", unit="cd/m2", low=0.0, high=900.0)]))
    assert [f.code for f in unmeasured] == ["uncalibrated-color"]
    assert "Y=P(name='Y')" in unmeasured[0].detail
    unbounded = check(written(red, [Param("Y", unit="cd/m2")]), calibration=PANEL)
    assert [f.code for f in unbounded] == ["bad-block"]
    assert "xyY.Y is parameter 'Y'" in unbounded[0].detail
    assert "cannot be bounded" in unbounded[0].detail


def test_an_xyy_is_checked_at_every_combination_of_its_parameters():
    """Each value of one parameter with each value of the other: only the redder chromaticity
    at the higher luminance is outside this panel, and pairing the values in order misses
    it."""
    def ranging(high):
        return replace(a_task(Disc(color=xyY(P("x"), 0.33, P("Y")))),
                       params=[Param("x", unit="chromaticity", choices=(0.64, 0.3127)),
                               Param("Y", unit="cd/m2", low=10.0, high=high)])
    assert codes(ranging(40.0)) == set()
    assert codes(ranging(60.0)) == {"unrealizable-color"}


def test_a_component_of_an_xyy_that_is_no_number_is_refused_not_raised():
    """Under a calibration this raised TypeError from the gamut test (A1 follow-ups, Task 1's
    review)."""
    stringly = a_task(Disc(color=xyY(0.3, "0.3", 10.0)))
    for calibration in (PANEL, None):
        found = check(stringly, calibration=calibration)
        assert any(f.code == "bad-block" and "xyY.y is '0.3', not a number" in f.detail
                   for f in found), (calibration, found)
    assert codes(stringly) == {"bad-block"}
