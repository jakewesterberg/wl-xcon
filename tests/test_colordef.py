"""A new color, three ways, and the proposed file it is written as (`wl_xcon.colordef`; the console
settings design's §6; its plan's Task 8; the PI, 2026-11-16: "1,2,or 3. you select an option and
then enter the info", "Saved into a color set file").

The set is wl-xcon's copy of isohue with its design frame added (`tests/fixtures/isohue_design.json`;
wl-xtasks' file gains the field in the plan's Task 11). Arithmetic only: nothing here is a
measurement.
"""

from __future__ import annotations

import json
import math
from importlib import metadata
from pathlib import Path

import pytest

from wl_xcon import colordef, cones, photometry
from wl_xcon.photometry import SRGB, ColorSet, _apply3, _held_light, _inverse3

FIXTURES = Path(__file__).parent / "fixtures"
ISOHUE = ColorSet.load(FIXTURES / "isohue_design.json")
PLAIN = ColorSet.load(FIXTURES / "isohue.json")
TO_LMS2 = _inverse3(cones.LMS_TO_XYZ_F2)
WHO = dict(by="jake (box, unverified)", rig="rig-a", on="2026-11-18")


def _cones(xy, luminance: float = 15.0) -> tuple[float, float, float]:
    """The 2° cone excitations of `xy` at `luminance` cd/m² of macaque luminance on the sRGB
    standard."""
    return _apply3(TO_LMS2, _held_light(tuple(xy), luminance, SRGB))


def test_a_set_reads_its_design_and_refuses_another():
    """`ColorSet.design` is the file's `{"space": "CAM16-UCS", "gray_lightness", "chroma"}`; any
    other space, a missing or an extra field, or a lightness or chroma no frame has is refused."""
    assert ISOHUE.design == {"space": "CAM16-UCS", "gray_lightness": 65.0, "chroma": 29.49}
    assert PLAIN.design is None
    data = json.loads((FIXTURES / "isohue_design.json").read_text())
    for design in ({**data["design"], "space": "CIELAB"}, {"space": "CAM16-UCS", "chroma": 29.49},
                   {**data["design"], "white": 1.0}, {**data["design"], "gray_lightness": 0.0},
                   {**data["design"], "gray_lightness": 101.0}, {**data["design"], "chroma": -1.0},
                   {**data["design"], "chroma": True}, "CAM16-UCS"):
        with pytest.raises(ValueError, match="design"):
            ColorSet(**{**data, "design": design})


def test_hue_angle_is_refused_for_a_set_with_no_design():
    with pytest.raises(ValueError, match="has no design"):
        colordef.chromaticity(PLAIN, "hue_angle", {"hue_deg": 140.0})
    with pytest.raises(ValueError, match="design frame is its file's"):
        colordef.chromaticity(ISOHUE, "hue_angle",
                              {"hue_deg": 140.0, "gray_lightness": 60.0, "chroma": 20.0})


def test_hue_angle_holds_the_grays_macaque_luminance_at_the_designs_chroma():
    """A hue angle's light has the gray's macaque luminance (its J′ bisected for it) and lies the
    design's chroma from the gray in a′b′, at that angle."""
    from wl_xcon import cam16

    frame = colordef.frame(ISOHUE)
    (_, a0, b0), target = colordef.gray_ucs(frame)
    x, y = colordef.chromaticity(ISOHUE, "hue_angle", {"hue_deg": 200.0})
    unit = (x / y, 1.0, (1.0 - x - y) / y)
    light = tuple(target / colordef._macaque(unit) * u for u in unit)
    _, a, b = cam16.to_ucs(light)
    assert math.hypot(a - a0, b - b0) == pytest.approx(29.49, abs=1e-6)
    assert math.degrees(math.atan2(b - b0, a - a0)) % 360.0 == pytest.approx(200.0, abs=1e-6)


def test_dkl_at_azimuth_and_elevation_zero_lies_on_the_l_m_axis():
    """Azimuth 0 and elevation 0 is the `l_m` axis (COL-32's axes, the luminance L + M at L:M 1, the
    set's own observer): S and L + M as the gray has them, L raised, to 1e-9 -- read in ratio, since
    a set's file writes a chromaticity and the set holds its luminance. Azimuth 90 moves S alone;
    elevation 90 is the gray's own chromaticity."""
    gray = _cones(ISOHUE.apex)
    xy = colordef.chromaticity(ISOHUE, "dkl",
                               {"azimuth_deg": 0.0, "elevation_deg": 0.0, "contrast": 0.05})
    moved = _cones(xy)
    scale = (gray[0] + gray[1]) / (moved[0] + moved[1])
    L, M, S = (v * scale for v in moved)
    assert abs(S / gray[2] - 1.0) < 1e-9
    assert L > gray[0] and M < gray[1]
    pooled = math.hypot(L / gray[0] - 1.0, M / gray[1] - 1.0)
    assert pooled == pytest.approx(0.05, abs=1e-9)
    up = _cones(colordef.chromaticity(ISOHUE, "dkl", {"azimuth_deg": 90.0, "elevation_deg": 0.0,
                                                      "contrast": 0.3}))
    scale = gray[0] / up[0]
    assert abs(up[1] * scale / gray[1] - 1.0) < 1e-9 and up[2] * scale > gray[2]
    top = colordef.chromaticity(ISOHUE, "dkl", {"azimuth_deg": 0.0, "elevation_deg": 90.0,
                                                "contrast": 0.2})
    assert max(abs(a - b) for a, b in zip(top, ISOHUE.apex)) < 1e-9


def test_a_dkl_colors_contrast_defaults_to_the_sets_mean_radius():
    """With no contrast, a DKL color stands the mean DKL radius of the set's colors from its gray
    (the planner's call); a new set, with no colors, must name one."""
    frame = colordef.frame(ISOHUE)
    radius = colordef.mean_radius(frame)
    radii = [math.hypot(*colordef.dkl_of(frame, xy)) for xy in ISOHUE.colors.values()]
    assert radius == pytest.approx(sum(radii) / 4, rel=1e-12) and radius > 0.0
    given = colordef.chromaticity(ISOHUE, "dkl", {"azimuth_deg": 90.0, "elevation_deg": 0.0})
    assert math.hypot(*colordef.dkl_of(frame, given)) == pytest.approx(radius, rel=1e-9)
    assert colordef.dkl_of(frame, given)[0] == pytest.approx(0.0, abs=1e-9)
    empty = colordef.new_set("teals", "dkl", {})
    with pytest.raises(ValueError, match="names its contrast"):
        colordef.chromaticity(empty, "dkl", {"azimuth_deg": 90.0, "elevation_deg": 0.0})


def test_xy_is_taken_as_given_and_one_no_light_has_is_refused():
    assert colordef.chromaticity(ISOHUE, "xy", {"x": 0.25, "y": 0.35}) == (0.25, 0.35)
    for x, y in ((0.7, 0.4), (-0.1, 0.3), (0.3, 0.0)):
        with pytest.raises(ValueError, match="no light has"):
            colordef.chromaticity(ISOHUE, "xy", {"x": x, "y": y})
    for numbers in ({"x": 0.25}, {"x": 0.25, "y": 0.35, "z": 0.4}, {"x": 0.25, "y": float("nan")},
                    {"x": "0.25", "y": 0.35}):
        with pytest.raises(ValueError):
            colordef.chromaticity(ISOHUE, "xy", numbers)
    with pytest.raises(ValueError, match="hue_angle, dkl, xy"):
        colordef.chromaticity(ISOHUE, "lab", {"x": 0.25, "y": 0.35})


def test_a_proposal_is_the_sets_file_plus_the_color_and_its_source(tmp_path):
    """The set's whole file with the color added: it loads with `ColorSet.load`, its old colors
    identical, its design kept, the new one at five places, and its source extended by who
    defined it, where, when and how."""
    xy = colordef.chromaticity(ISOHUE, "hue_angle", {"hue_deg": 200.0})
    data = colordef.proposal(ISOHUE, "cyan", xy, method="hue_angle", numbers={"hue_deg": 200.0},
                             **WHO)
    path = tmp_path / "isohue.json"
    path.write_text(json.dumps(data))
    loaded = ColorSet.load(path)
    assert list(loaded.colors) == [*ISOHUE.colors, "cyan"]
    assert all(loaded.colors[name] == ISOHUE.colors[name] for name in ISOHUE.colors)
    assert loaded.colors["cyan"] == colordef.written(xy)
    assert (loaded.apex, loaded.luminance_cd_m2, loaded.held, loaded.design) == (
        ISOHUE.apex, ISOHUE.luminance_cd_m2, ISOHUE.held, ISOHUE.design)
    assert loaded.source.startswith(ISOHUE.source)
    assert loaded.source.endswith(
        f"cyan: hue_angle (hue_deg 200), defined on rig-a by jake (box, unverified) on "
        f"2026-11-18 (wl-xcon {metadata.version('wl-xcon')}), proposed for review.")


def test_a_proposal_refuses_a_name_in_the_set_or_one_no_card_can_show():
    for name in ("green", "x" * 41, "", "   ", "tab\there"):
        with pytest.raises(ValueError):
            colordef.proposal(ISOHUE, name, (0.25, 0.35), method="xy",
                              numbers={"x": 0.25, "y": 0.35}, **WHO)
    assert "x" * 40 in colordef.proposal(ISOHUE, "x" * 40, (0.25, 0.35), method="xy",
                                         numbers={"x": 0.25, "y": 0.35}, **WHO)["colors"]


def test_a_new_set_takes_the_d65_apex_fifteen_cd_and_a_design_from_its_first_hue_angle():
    numbers = {"hue_deg": 90.0, "gray_lightness": 60.0, "chroma": 20.0}
    frame = colordef.new_set("warm", "hue_angle", numbers)
    assert (frame.apex, frame.luminance_cd_m2, frame.design) == (
        (0.31272, 0.32900), 15.0, {"space": "CAM16-UCS", "gray_lightness": 60.0, "chroma": 20.0})
    xy = colordef.chromaticity(frame, "hue_angle", numbers)
    data = colordef.proposal(frame, "amber", xy, method="hue_angle", numbers=numbers, **WHO)
    assert (data["name"], list(data["colors"]), data["held"], data["design"]) == (
        "warm", ["amber"], "macaque_2deg_LM1", frame.design)
    assert data["source"].startswith("amber: hue_angle (hue_deg 90, gray_lightness 60, chroma 20)")
    assert colordef.new_set("cool", "xy", {"x": 0.2, "y": 0.3}).design is None
    with pytest.raises(ValueError, match="gray_lightness and chroma"):
        colordef.new_set("warm", "hue_angle", {"hue_deg": 90.0})
    for name in ("../isohue", "a/b", "", "x" * 41, "-lead", "é"):
        with pytest.raises(ValueError, match="named by"):
            colordef.new_set(name, "xy", {"x": 0.2, "y": 0.3})
