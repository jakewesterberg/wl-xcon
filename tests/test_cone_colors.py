"""Cone colors as lights (engine spec §7.4; engine build A2): a `DKL` color is a contrast about
the background in the lab's observer, and a calibration turns it into CIE XYZ -- the standard
through the CIE's matrix (A2's Q2), a measured one through its spectra."""

import math
from dataclasses import replace

import pytest

from _calibrations import SPECTRA, measured
from wl_xcon import cones
from wl_xcon.photometry import (
    D65,
    DKL,
    SRGB,
    ConeContrast,
    Spectra,
    _apply3,
    background_cones,
    cone_contrast,
    cone_xyz,
    xyY,
)
from wl_xcon.task import P

GRAY = xyY(*D65, 40.0)


def _luminance_f10(excited) -> float:
    return cones.V_F10[0] * excited[0] + cones.V_F10[1] * excited[1]


def test_the_standard_converts_through_the_inverse_of_the_cies_matrix():
    """A2's Q2 (COL-18): computed 2026-10-09 from Stockman and Rider (2023), Eq. 15."""
    assert [v for row in SRGB.cones for v in row] == pytest.approx(
        [0.21701045, 0.83573367, -0.0435106,
         -0.42997951, 1.20388946, 0.0862109,
         0.0, 0.0, 0.46579234], abs=1e-8)


def test_on_the_standard_v_f10_is_the_standards_own_luminance():
    """The CIE's matrix sends V_F,10 to Y, so on the default the two luminances agree."""
    for light in (GRAY, xyY(0.64, 0.33, 17.0), xyY(0.15, 0.06, 5.0)):
        assert _luminance_f10(background_cones(SRGB, light)) == pytest.approx(light.Y, rel=1e-12)


def test_dkl_luminance_is_luminance_contrast():
    X, Y, Z = cone_xyz(DKL(lum=0.1), SRGB, GRAY)

    assert Y == pytest.approx(44.0, rel=1e-12)
    assert (X / (X + Y + Z), Y / (X + Y + Z)) == pytest.approx(D65, abs=1e-12)


def test_dkl_red_green_is_pooled_cone_contrast_at_the_isoluminant_ratio():
    """COL-07: `l_m=0.08` is a pooled cone contrast of 0.08, L up and M down at the ratio V_F,10
    holds still, S untouched. On a D65 background on the default that ratio is -2.2165
    (computed 2026-10-09; the A2 research note's §2 gives about -2.2 on its modeled displays)."""
    contrast = cone_contrast(DKL(l_m=0.08), SRGB, GRAY)

    assert math.hypot(*contrast) == pytest.approx(0.08, rel=1e-12)
    assert contrast[0] > 0 > contrast[1] and contrast[2] == 0.0
    assert contrast[1] / contrast[0] == pytest.approx(-2.2164975677, rel=1e-9)
    assert cone_xyz(DKL(l_m=0.08), SRGB, GRAY) == pytest.approx(
        (44.04969059, 40.0, 43.56231003), rel=1e-8)


def test_lum_zero_is_isoluminant_in_the_labs_observer_on_any_calibration():
    """A2's Q5: isoluminance is V_F,10's, by construction, on the standard and on a measured panel."""
    for panel, background in ((SRGB, GRAY), (measured(), xyY(0.3127, 0.329, 20.0))):
        before = _luminance_f10(background_cones(panel, background))
        for color in (DKL(l_m=0.08), DKL(l_m=-0.05, s_lm=0.3), DKL(s_lm=-0.4)):
            after = _luminance_f10(_apply3(panel.cones, cone_xyz(color, panel, background)))
            assert after == pytest.approx(before, rel=1e-9), (panel.id, color)


def test_dkl_s_is_s_cone_contrast_alone():
    assert cone_contrast(DKL(s_lm=0.5), SRGB, GRAY) == (0.0, 0.0, 0.5)
    assert cone_xyz(DKL(s_lm=0.5), SRGB, GRAY) == pytest.approx(
        (42.38535887, 40.0, 65.34346505), rel=1e-8)


def test_the_three_axes_add():
    together = cone_contrast(DKL(lum=0.05, l_m=0.08, s_lm=-0.2), SRGB, GRAY)
    apart = [cone_contrast(c, SRGB, GRAY) for c in (DKL(lum=0.05), DKL(l_m=0.08), DKL(s_lm=-0.2))]

    assert together == pytest.approx(tuple(map(sum, zip(*apart))), rel=1e-12)


def test_a_cone_color_on_black_names_no_light():
    with pytest.raises(ValueError, match="background is black"):
        cone_xyz(DKL(l_m=0.08), SRGB, xyY(*D65, 0.0))


def test_a_measured_calibration_converts_through_its_spectra():
    """Each primary at full drive has exactly the excitations its spectrum gives."""
    panel = measured()

    for channel, primary in (("red", panel.red), ("green", panel.green), ("blue", panel.blue)):
        expected = cones.excitations(SPECTRA.nm, getattr(SPECTRA, channel))
        assert background_cones(panel, primary) == pytest.approx(expected, rel=1e-9), channel


def test_a_measured_calibration_without_spectra_converts_no_cone_color():
    panel = measured(spectra=None)

    assert panel.cones is None
    with pytest.raises(ValueError, match="measured without spectra"):
        cone_xyz(DKL(l_m=0.08), panel, xyY(0.3127, 0.329, 20.0))


def test_a_measured_calibration_names_its_observer():
    with pytest.raises(ValueError, match="names the observer"):
        measured(observer=" ")


def test_the_standard_has_no_spectra():
    with pytest.raises(ValueError, match="no spectra"):
        replace(SRGB, spectra=SPECTRA)


@pytest.mark.parametrize("change, said", [
    (dict(nm=(390.0,)), "tuple of finite wavelengths"),
    (dict(nm=SPECTRA.nm[:-1] + (float("inf"),)), "tuple of finite wavelengths"),
    (dict(nm=(390.0, 390.0) + SPECTRA.nm[2:]), "rise strictly"),
    (dict(nm=tuple(nm + 15.0 for nm in SPECTRA.nm)), "cover 390 to 780"),
    (dict(nm=tuple(nm - 15.0 for nm in SPECTRA.nm)), "cover 390 to 780"),
    (dict(red=SPECTRA.red[:-1]), "one radiance at each"),
    (dict(green=list(SPECTRA.green)), "as a tuple"),
    (dict(blue=SPECTRA.blue[:-1] + (-1.0,)), "none negative"),
    (dict(blue=(0.0,) * len(SPECTRA.nm)), "not all zero"),
    (dict(red=SPECTRA.red[:-1] + (float("nan"),)), "finite radiances"),
])
def test_spectra_that_are_not_a_measurement_are_refused(change, said):
    fields = dict(nm=SPECTRA.nm, red=SPECTRA.red, green=SPECTRA.green, blue=SPECTRA.blue)
    fields.update(change)

    with pytest.raises(ValueError, match=said):
        Spectra(**fields)


def test_spectra_sampled_more_coarsely_than_the_cie_table_are_refused():
    nm = tuple(float(v) for v in range(380, 781, 10))

    with pytest.raises(ValueError, match="gap of 10 nm"):
        Spectra(nm=nm, red=(1.0,) * len(nm), green=(1.0,) * len(nm), blue=(1.0,) * len(nm))


def test_a_calibration_converts_its_spectra_once_as_it_is_built(monkeypatch):
    """Call 27: `cones` is computed when the calibration is built, not on each read."""
    calls = []
    real = cones.excitations
    monkeypatch.setattr(cones, "excitations", lambda nm, r: calls.append(1) or real(nm, r))

    panel = measured()
    first = panel.cones
    for _ in range(5):
        assert panel.cones is first

    assert len(calls) == 3


def test_a_component_that_is_not_a_number_is_a_value_error_never_a_type_error():
    """Call 28: every caller's `except ValueError` holds it."""
    with pytest.raises(ValueError, match="not a number"):
        cone_xyz(DKL(l_m=P("c")), SRGB, GRAY)


def test_a_cone_contrast_is_its_own_three_numbers():
    background = background_cones(SRGB, GRAY)
    lit = _apply3(SRGB.cones, cone_xyz(ConeContrast(L=0.1, S=-0.3), SRGB, GRAY))

    assert cone_contrast(ConeContrast(L=0.1, M=-0.05, S=0.3), SRGB, GRAY) == (0.1, -0.05, 0.3)
    assert [after / before - 1.0 for after, before in zip(lit, background)] == pytest.approx(
        [0.1, 0.0, -0.3], abs=1e-12)
