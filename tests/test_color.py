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

from _calibrations import LINEAR, measured
from wl_xcon import cones, look
from wl_xcon.check import _background_lights, check
from wl_xcon.cones import CIE2006_10
from wl_xcon.findings import NOT_RECORDING
from wl_xcon.photometry import (
    D65,
    DKL,
    RMS,
    SRGB,
    Calibration,
    ConeContrast,
    Gray,
    Michelson,
    Weber,
    to_xyz,
    xyY,
)
from wl_xcon.task import (
    RDS,
    REMEMBERED,
    After,
    Array,
    Checkerboard,
    Disc,
    Noise,
    On,
    Outcome,
    P,
    Param,
    Plaid,
    Show,
    Square,
    State,
    Stimulus,
    Trial,
    Update,
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

#: A lit gray background, for a color relative to it.
GRAY_BG = Gray(20.0)


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
    # With no calibration a Gray is not flagged here; on the default calibration it is the
    # session's one warning (`warnlist.of_calibration`, accepted at the open).
    assert codes(a_task(Disc(size=1.0, color=Gray(40.0))), calibration=None) == set()


def test_isoluminance_is_a_named_observers_and_a_calibration_names_its_own():
    """`DKL(lum=0)` is isoluminant *by construction*, against a named observer: the lab's, the
    CIE 2006 10° observer's V_F,10 (A2's Q5; COL-17), named in code and recorded with each
    session. A measured calibration still says whose luminous efficiency its own luminances were
    measured against, or it does not load: an unlabeled cd/m² is a claim nobody can check."""
    assert CIE2006_10.luminosity == "V_F,10"
    with pytest.raises(ValueError, match="names the observer"):
        Calibration(red=PANEL.red, green=PANEL.green, blue=PANEL.blue, background=PANEL.background,
                    transfer=(LINEAR,) * 3, observer="", measured_on="2026-08-31")


def test_a_cone_color_the_panel_cannot_make_on_its_background_is_refused():
    """Full conversion, not a stored maximum (engine spec §7.4; COL-08): a red-green contrast the
    old 0.85 gate passed is outside the panel's gamut."""
    trial = replace(a_task(Disc(color=DKL(l_m=-0.5))), background=GRAY_BG)

    found = _found(trial, calibration=measured())

    assert found["unrealizable-color"].detail.startswith(
        "Disc asks for DKL(lum=0.0, l_m=-0.5, s_lm=0.0) on a background of "
        "xyY(x=0.3127, y=0.329, Y=20.0)")
    assert "outside [0, 1]" in found["unrealizable-color"].detail
    assert "unrealizable-color" not in _found(
        replace(a_task(Disc(color=DKL(l_m=0.08))), background=GRAY_BG), calibration=measured())


def test_a_cone_color_on_a_measured_calibration_without_spectra_is_refused():
    trial = replace(a_task(Disc(color=DKL(l_m=0.08))), background=GRAY_BG)

    assert "measured without spectra" in _found(trial, calibration=PANEL)["unrealizable-color"].detail


def test_a_cone_color_is_realizable_or_not_by_its_background():
    """COL-10: the same contrast fits on a dim gray and not on one near the panel's white."""
    color = Disc(color=DKL(lum=0.5))
    dim = replace(a_task(color), background=Gray(20.0))
    bright = replace(a_task(color), background=Gray(150.0))

    assert "unrealizable-color" not in _found(dim, calibration=measured())
    assert "unrealizable-color" in _found(bright, calibration=measured())


def test_a_cone_color_with_parameters_is_checked_at_each_value_they_can_take():
    """XC-269: a parameter inside a `DKL` raised TypeError from `DKL.magnitude()` under a measured
    calibration. Each component is read at each choice or both ends of its range, crossed."""
    trial = replace(a_task(Disc(color=DKL(lum=0.0, l_m=P("c")))), background=GRAY_BG,
                    params=[Param("c", unit="contrast", low=-0.6, high=0.1)])

    found = check(trial, calibration=measured())

    assert [f.detail.split(" on ")[0] for f in found if f.code == "unrealizable-color"] == [
        "Disc asks for DKL(lum=0.0, l_m=-0.6, s_lm=0.0)"]


def test_a_cone_contrast_is_checked_by_full_conversion_too():
    trial = replace(a_task(Disc(color=ConeContrast(S=P("s")))), background=GRAY_BG,
                    params=[Param("s", unit="contrast", choices=(0.5, 12.0))])

    details = [f.detail for f in check(trial, calibration=measured())
               if f.code == "unrealizable-color"]

    assert len(details) == 1 and "ConeContrast(L=0.0, M=0.0, S=12.0)" in details[0]


@pytest.mark.parametrize("field", ["L", "M", "S"])
def test_each_cone_contrast_component_is_a_number(field):
    trial = replace(a_task(Disc(color=ConeContrast(**{field: "much"}))), background=GRAY_BG)

    assert (f"ConeContrast.{field} is 'much', not a number"
            in _found(trial, calibration=measured())["bad-block"].detail)


def test_a_black_background_value_is_left_to_its_own_refusal():
    """`_background_lights` leaves black out, so a cone color is converted only against the lit
    values; `cone-color-on-black` refuses the black one."""
    trial = replace(a_task(Disc(color=DKL(l_m=-0.5))), background=P("bg"),
                    params=[Param("bg", unit="color", choices=(Gray(0.0), Gray(20.0)))])
    params = {p.name: p for p in trial.params}

    assert _background_lights(trial, params) == [xyY(*D65, 20.0)]
    found = check(trial, calibration=measured())
    assert {f.code for f in found} >= {"cone-color-on-black", "unrealizable-color"}
    assert all("Y=0.0" not in f.detail for f in found if f.code == "unrealizable-color")


def test_a_cone_table_that_is_not_the_cies_refuses_cone_colors_and_nothing_else(monkeypatch):
    """The review's E-I3: the checksum guard on the read path. Emptied cache, wrong checksum: the
    table read refuses; a measured calibration built then converts no cone color, saying why,
    and still checks a plain color."""
    monkeypatch.setattr(cones, "_TABLE", [])
    monkeypatch.setitem(cones.CIE_FILES, cones.TABLE, "0" * 64)
    with pytest.raises(ValueError, match="is not the CIE's file"):
        cones.table()

    panel = measured()

    assert panel.cones is None and "is not the CIE's file" in panel.cones_refused
    trial = replace(a_task(Disc(color=DKL(l_m=0.08))), background=GRAY_BG)
    assert "is not the CIE's file" in _found(trial, calibration=panel)["unrealizable-color"].detail
    assert _found(a_task(Disc(color=xyY(0.3, 0.35, 20.0))), calibration=panel) == {}


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


# --- Colors and lights on the default calibration (engine build B) ---------------------


def _found(trial, calibration=SRGB) -> dict:
    return {f.code: f for f in check(trial, calibration=calibration)}


def _choosing(*choices) -> Trial:
    """One stimulus whose appearance is a parameter offering `choices`."""
    return Trial(
        start="on",
        params=[Param("looks", unit="appearance", choices=choices)],
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
        states=[State("on", enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=P("looks")))],
                      go=[On(After(1.0), Outcome.ABORT)])],
    )


#: A contrast parameter with a range, as a staircase or a live edit would move it.
CONTRAST = Param("c", unit="contrast", low=0.1, high=0.9)


def test_isoluminance_needs_a_measured_calibration_in_every_kind():
    found = _found(a_task(Disc(color=DKL(lum=0.0, l_m=0.08))))

    assert found["isoluminance-on-default"].blocking
    assert "measured calibration" in found["isoluminance-on-default"].detail


def test_a_dkl_color_on_the_default_waits_for_build_a2():
    found = _found(a_task(Disc(color=DKL(lum=0.1))))

    assert found["dkl-on-default"].blocking and "A2" in found["dkl-on-default"].detail
    assert "isoluminance-on-default" not in found


def test_a_dkl_color_with_a_parameter_inside_is_refused_on_the_default_never_raised():
    """The review's I4: `DKL.magnitude()` raises on a parameter (XC-269), and from Task 8
    every session, `wlx check` and `wlx run` check against the default."""
    isoluminant = replace(a_task(Disc(color=DKL(lum=0.0, l_m=P("c")))),
                          params=[Param("c", unit="contrast", low=-0.1, high=0.1)])
    stepped = replace(a_task(Disc(color=DKL(lum=P("c"), l_m=0.05))),
                      params=[Param("c", unit="contrast", low=-0.1, high=0.1)])

    assert _found(isoluminant)["isoluminance-on-default"].blocking
    assert _found(stepped)["dkl-on-default"].blocking
    assert "isoluminance-on-default" not in _found(stepped)


def test_a_named_color_on_the_default_is_refused_only_in_recording():
    found = _found(a_task(Disc(color=xyY(0.64, 0.33, 10.0))))

    assert set(found) == {"color-on-default"}
    warning = found["color-on-default"]
    assert (warning.blocking, warning.accepted_in) == (False, NOT_RECORDING)
    assert "Disc" in warning.detail


def test_a_light_a_parameter_sets_is_refused_only_in_recording_on_the_default():
    trial = replace(a_task(Disc(color=Gray(P("lum")))),
                    params=[Param("lum", unit="cd/m2", low=0.0, high=80.0)])

    found = _found(trial)

    assert set(found) == {"contrast-on-default"}
    assert "'lum'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].accepted_in == NOT_RECORDING


def test_a_color_parameter_and_a_parameter_inside_its_choices_are_both_light_factors():
    trial = replace(a_task(Disc(color=P("col"))),
                    params=[Param("col", unit="color", choices=(Gray(P("lum")), Gray(10.0))),
                            Param("lum", unit="cd/m2", low=0.0, high=80.0)])

    detail = _found(trial)["contrast-on-default"].detail

    assert "'col'" in detail and "'lum'" in detail


@pytest.mark.parametrize("looks", [
    Checkerboard(contrast=Michelson(P("c"))),
    Plaid(contrast=Michelson(P("c"))),
    Noise(contrast=RMS(P("c"))),
    RDS(contrast=Michelson(P("c"))),
], ids=["checkerboard", "plaid", "noise", "rds"])
def test_a_patterns_contrast_a_parameter_sets_is_a_light_factor(looks):
    """The review's I5: `_light` has no reading of these appearances' lights (a later
    build defines them), so the walk reads their `contrast` field itself."""
    trial = replace(a_task(looks), params=[CONTRAST], background=Gray(20.0))

    assert "'c'" in _found(trial)["contrast-on-default"].detail


def test_noise_choices_that_differ_only_in_contrast_are_a_light_factor():
    """The review's I5: compared through `_light`, both choices read `None` and compared
    equal."""
    trial = replace(_choosing(Noise(contrast=RMS(0.1)), Noise(contrast=RMS(0.2))),
                    background=Gray(20.0))

    assert "'looks'" in _found(trial)["contrast-on-default"].detail


def test_a_looks_fill_and_outline_are_read_for_light_factors():
    choosing = _choosing(look.Look(fill=look.Flat(color=Gray(10.0))),
                         look.Look(fill=look.Flat(color=Gray(20.0))))
    outlined = replace(
        a_task(look.Look(fill=look.Flat(color=Gray(10.0)),
                         outline=look.Outline(width=0.1, color=Gray(P("lum"))))),
        params=[Param("lum", unit="cd/m2", low=0.0, high=80.0)])

    assert "'looks'" in _found(choosing)["contrast-on-default"].detail
    assert "'lum'" in _found(outlined)["contrast-on-default"].detail


def test_a_look_whose_whole_fill_is_a_parameter_is_a_light_factor_and_its_choices_are_read():
    """XC-271's shape (a `Look` whose fill is a parameter gets no light check): this
    finding does not inherit that blind spot."""
    trial = replace(a_task(look.Look(fill=P("fill"))), params=[
        Param("fill", unit="fill", choices=(look.Flat(color=Gray(10.0)),
                                            look.Flat(color=Gray(P("lum"))))),
        Param("lum", unit="cd/m2", low=0.0, high=80.0),
    ])

    detail = _found(trial)["contrast-on-default"].detail

    assert "'fill'" in detail and "'lum'" in detail


def test_a_looks_outline_of_another_kind_or_written_as_a_parameter_never_raises_on_the_default():
    """A `Look` whose outline is not an `Outline` is refused (`bad-block`), and one written as
    a parameter loads (XC-273); `check()` raises on neither since the A1 follow-ups' fix wave,
    and asking either for its color here would raise again. A parameter that is a whole
    outline counts, as a whole fill does, and its choices' colors are read; their widths are
    no light."""
    thin = a_task(look.Look(fill=look.Flat(color=Gray(10.0)), outline="thin"))
    chosen = replace(a_task(look.Look(fill=look.Flat(color=Gray(10.0)), outline=P("o"))), params=[
        Param("o", unit="outline", choices=(look.Outline(width=P("w"), color=Gray(P("lum"))),)),
        Param("w", unit="deg", low=0.05, high=0.1),
        Param("lum", unit="cd/m2", low=0.0, high=80.0),
    ])

    assert "bad-block" in _found(thin) and "contrast-on-default" not in _found(thin)
    detail = _found(chosen)["contrast-on-default"].detail
    assert "'o'" in detail and "'lum'" in detail and "'w'" not in detail


def test_a_background_a_parameter_sets_is_a_light_factor():
    trial = replace(a_task(Disc(size=1.0, color=Gray(10.0))), background=Gray(P("bg")),
                    params=[Param("bg", unit="cd/m2", low=0.0, high=20.0)])

    assert "'bg'" in _found(trial)["contrast-on-default"].detail


def test_a_light_parameter_undeclared_or_among_its_own_choices_is_refused_never_raised():
    """From Task 8 every session checks against the default, so the walk's own guards are
    what keep `check()` from raising on either: an undeclared parameter has no choices to
    read, and one met again inside its own choices is `_self_referring`'s refusal."""
    undeclared = a_task(Disc(color=Gray(P("lum"))))
    itself = replace(a_task(Disc(color=P("col"))),
                     params=[Param("col", unit="color", choices=(Gray(P("col")), Gray(10.0)))])

    assert "undeclared-parameter" in _found(undeclared)
    assert "'lum'" in _found(undeclared)["contrast-on-default"].detail
    assert any("refers to itself" in f.detail for f in check(itself, calibration=SRGB))
    assert "'col'" in _found(itself)["contrast-on-default"].detail


def test_a_per_eye_background_a_parameter_sets_is_a_light_factor():
    trial = replace(a_task(Disc(size=1.0, color=Gray(10.0))), view="stereoscope",
                    background_left=Gray(P("left")),
                    params=[Param("left", unit="cd/m2", low=0.0, high=20.0)])

    assert "'left'" in _found(trial)["contrast-on-default"].detail


def test_a_gratings_frequency_phase_speed_and_direction_are_no_light():
    """`_lit` reads a fill's `color`, `contrast` and `mean`, never the rest of it."""
    grating = look.SineGrating(sf=P("sf"), phase=P("ph"), tf=P("tf"), direction=P("dir"),
                               contrast=Michelson(0.5), mean=Gray(P("lum")))
    trial = replace(a_task(look.Look(fill=grating)), background=Gray(20.0), params=[
        Param("sf", unit="cyc/deg", low=1.0, high=4.0),
        Param("ph", unit="deg", low=0.0, high=360.0),
        Param("tf", unit="Hz", low=0.0, high=4.0),
        Param("dir", unit="deg", choices=(90.0, 270.0)),
        Param("lum", unit="cd/m2", low=10.0, high=40.0),
    ])

    detail = _found(trial)["contrast-on-default"].detail

    assert "'lum'" in detail
    assert not any(f"'{name}'" in detail for name in ("sf", "ph", "tf", "dir"))


def _showing(opacity=1.0, *later) -> Trial:
    """One gray disc, shown at `opacity`, then the actions `later`."""
    return Trial(
        start="on",
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
        states=[
            State("on", enter=[Show(Stimulus("s", at=(0.0, 0.0), opacity=opacity,
                                             looks=Disc(size=1.0, color=Gray(10.0))))],
                  go=[On(After(1.0), "later")]),
            State("later", enter=list(later), go=[On(After(1.0), Outcome.ABORT)]),
        ],
    )


def test_an_opacity_a_parameter_sets_when_shown_is_a_light_factor():
    """Spec §4.4: front covers back by its opacity, so an opacity a parameter sets sets the
    light shown (Task 4's review)."""
    trial = replace(_showing(P("op")), params=[Param("op", unit="fraction", low=0.2, high=1.0)])

    found = _found(trial)

    assert "'op'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].refuses("recording")


def test_an_opacity_a_parameter_sets_in_an_update_is_a_light_factor():
    trial = replace(_showing(1.0, Update("s", opacity=P("op"))),
                    params=[Param("op", unit="fraction", choices=(0.5, 1.0))])

    found = _found(trial)

    assert "'op'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].refuses("recording")
    assert "contrast-on-default" not in _found(_showing(1.0, Update("s", at=(1.0, 0.0))))


def _array(item, among=None) -> Array:
    return Array(looks=item, among=Disc(size=1.0, color=Gray(10.0)) if among is None else among)


def test_a_parameter_choosing_between_arrays_that_differ_only_in_light_is_a_factor():
    """Task 4's review: `_lit` reads an `Array` as no light, so these compared equal. An
    array's items are read in turn, and a parameter among them through its choices."""
    gray = _choosing(_array(Disc(size=1.0, color=Gray(10.0))),
                     _array(Disc(size=1.0, color=Gray(20.0))))
    looks = replace(_choosing(_array(look.Look(fill=look.Flat(color=Gray(10.0)))),
                              _array(look.Look(fill=look.Flat(color=Gray(20.0))))),
                    background=Gray(20.0))
    through = _choosing(_array(P("a")), _array(P("b")))
    through = replace(through, params=[
        *through.params,
        Param("a", unit="appearance", choices=(Disc(size=1.0, color=Gray(10.0)),)),
        Param("b", unit="appearance", choices=(Disc(size=1.0, color=Gray(20.0)),)),
    ])

    for trial in (gray, looks, through):
        found = _found(trial)
        assert "'looks'" in found["contrast-on-default"].detail
        assert found["contrast-on-default"].refuses("recording")
    assert "'a'" not in _found(through)["contrast-on-default"].detail


def test_arrays_whose_items_differ_only_in_shape_are_not_a_light_factor():
    """Shape-only choices stay clean when they are arrays (the twin of
    `test_an_appearance_whose_choices_differ_only_in_shape_is_not_a_light_factor`), and a
    parameter named among an array's items is no light factor for being named there: the
    search task's shape-only case."""
    disc, square = Disc(size=1.0, color=Gray(10.0)), Square(size=1.0, color=Gray(10.0))
    literal = _choosing(_array(disc), _array(square))
    through = _choosing(_array(P("a")), _array(P("b")))
    through = replace(through, params=[*through.params,
                                       Param("a", unit="appearance", choices=(disc,)),
                                       Param("b", unit="appearance", choices=(square,))])
    direct = replace(a_task(Array(looks=P("t"), among=P("d"))), params=[
        Param("t", unit="appearance", choices=(disc, square)),
        Param("d", unit="appearance", choices=(square, disc)),
    ])

    for trial in (literal, through, direct):
        assert "contrast-on-default" not in _found(trial)


def test_each_choice_of_an_appearance_parameter_is_named_in_its_own_finding():
    """Task 4's review: the search task's five isoluminant choices were five identical lines."""
    red, green = DKL(lum=0.0, l_m=0.08), DKL(lum=0.0, l_m=-0.08)
    found = check(_choosing(Disc(size=1.0, color=red), Square(size=1.0, color=green)),
                  calibration=SRGB)

    details = [f.detail for f in found if f.code == "isoluminance-on-default"]

    assert len(details) == 2
    assert details[0].startswith("Disc (choice 1 of parameter 'looks') claims isoluminance")
    assert details[1].startswith("Square (choice 2 of parameter 'looks') claims isoluminance")
    shared = Disc(size=1.0, color=red)
    twice = replace(_choosing(shared), params=[
        Param("looks", unit="appearance", choices=(shared,)),
        Param("other", unit="appearance", choices=(Square(size=1.0, color=green), shared)),
    ])
    assert any(f.detail.startswith(
        "Disc (choice 1 of parameter 'looks', choice 2 of parameter 'other') claims")
        for f in check(twice, calibration=SRGB))


def test_an_appearance_whose_choices_differ_in_light_is_a_factor_too():
    found = _found(_choosing(Disc(size=1.0, color=Gray(10.0)), Disc(size=1.0, color=Gray(20.0))))

    assert "'looks'" in found["contrast-on-default"].detail


def test_an_appearance_whose_choices_differ_only_in_shape_is_not_a_light_factor():
    assert "contrast-on-default" not in _found(
        _choosing(Disc(size=1.0, color=Gray(10.0)), Square(size=1.0, color=Gray(10.0))))


def test_a_literal_gray_on_the_default_is_the_sessions_warning_not_the_tasks():
    """Absolute luminance on the default is the session's one warning
    (`warnlist.of_calibration`), never a finding per stimulus."""
    assert _found(a_task(Disc(size=1.0, color=Gray(40.0)))) == {}


def test_a_gray_above_the_defaults_white_cannot_be_shown_on_it():
    assert "unrealizable-color" in _found(a_task(Disc(size=1.0, color=Gray(80.5))))


def test_a_measured_calibration_brings_none_of_the_defaults_findings():
    assert _found(a_task(Disc(color=xyY(0.500, 0.400, 30.0))), calibration=PANEL) == {}


# --- Cone colors need a lit background, and one (engine build A2) -----------------------------


def test_a_cone_color_on_the_black_default_background_is_refused_naming_the_fix():
    """Spec §7.5 (the PI, N§4 batch 3: "It must declare one"; A1's call 6)."""
    found = _found(a_task(Disc(color=DKL(l_m=0.08))), calibration=measured())

    assert found["cone-color-on-black"].blocking
    assert found["cone-color-on-black"].detail.startswith("Disc: a cone color is relative")
    assert "declare the trial's background" in found["cone-color-on-black"].detail


def test_a_cone_color_on_a_background_a_parameter_can_make_black_is_refused():
    trial = replace(a_task(Disc(color=DKL(l_m=0.08))), background=Gray(P("bg")),
                    params=[Param("bg", unit="cd/m2", low=0.0, high=40.0)])

    found = _found(trial, calibration=measured())

    assert "raise the low end of parameter 'bg'" in found["cone-color-on-black"].detail


def test_a_cone_color_on_a_lit_background_is_not_refused_for_it():
    trial = replace(a_task(Disc(color=DKL(l_m=0.08))), background=GRAY_BG)

    assert "cone-color-on-black" not in _found(trial, calibration=measured())


def test_one_finding_names_every_cone_colored_carrier():
    found = _found(_choosing(Disc(size=1.0, color=DKL(l_m=0.08)),
                             Square(size=1.0, color=DKL(l_m=-0.08))), calibration=measured())

    assert found["cone-color-on-black"].detail.startswith(
        "Disc (choice 1 of parameter 'looks'); Square (choice 2 of parameter 'looks'): ")


def test_a_cone_color_between_two_eyes_backgrounds_that_differ_is_refused():
    trial = replace(a_task(Disc(color=DKL(l_m=0.08))), view="stereoscope",
                    background_left=Gray(20.0), background_right=Gray(30.0))

    assert _found(trial, calibration=measured())["cone-color-two-backgrounds"].blocking
    same = replace(trial, background_left=Gray(20.0), background_right=Gray(20.0))
    assert "cone-color-two-backgrounds" not in _found(same, calibration=measured())


def test_a_background_is_an_absolute_light():
    trial = replace(a_task(Disc(size=1.0, color=Gray(40.0))), background=DKL(lum=0.1))

    found = _found(trial, calibration=measured())

    assert "not an absolute light" in found["bad-block"].detail


@pytest.mark.parametrize("field", ["lum", "l_m", "s_lm"])
def test_each_dkl_component_is_a_number(field):
    trial = replace(a_task(Disc(color=DKL(**{field: "much"}))), background=GRAY_BG)

    assert f"DKL.{field} is 'much', not a number" in _found(trial)["bad-block"].detail
