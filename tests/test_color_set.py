"""A color set held at a macaque cone luminance (the pop-out search plan, Task 2; its spec, §3.2 and
§5 item 4): wl-style's isohue colors, given by their CIE 1931 chromaticities, each realized on the
rig's panel so that its luminance for a macaque observer -- L + M at L:M 1 on the 2° cone
fundamentals (the CIE 2006 2° table, Stockman and Sharpe's), as wl-style computes it (the PI,
2026-11-07: "wl-style's 2-degree set") -- equals that of a D65 light at the set's 15 cd/m² ("15
cd/m² on every rig"). A panel that cannot show all of them there moves all of them toward the
set's apex by one shared fraction, never a luminance change and never a clipped color, and the
load check says by how much."""

from __future__ import annotations

import hashlib
import json
import re
from importlib import resources
from pathlib import Path

import numpy as np
import pytest

from _calibrations import NM, SPECTRA, measured
from wl_xcon import cones, photometry
from wl_xcon.check import check
from wl_xcon.declarations import canonical
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.photometry import D65, SRGB, xyY
from wl_xcon.task import After, Disc, On, Outcome, P, Param, Show, State, Stimulus, Trial, Window

#: The set as the tests read it: the shape of wl-xtasks' `stimuli/isohue.json` (plan, Task 9).
FIXTURE = Path(__file__).parent / "fixtures" / "isohue.json"
COLORS = ("blue", "purple", "red", "green")

#: wl-style's sRGB previews of the four (isohue_levels.csv, cone_macaque_equal, saturation 1; the
#: green from its generator, 2026-11-07) and of its reference gray, the sector's apex.
PREVIEWS = {"blue": "#2f93f8", "purple": "#bc79e0", "red": "#ed7474", "green": "#54a947"}
GRAY = "#969696"

#: The CIE 2006 2° table's sha256, its metadata's (`checksums`; ADR-0012, amended 2026-11-07).
TABLE_2DEG_SHA256 = "f48160edf11c1a121aaaf41d4c3b7513385bfc9c60d726b88e735519f6d37b1f"

#: wl-style's own macaque luminance of the tests' panel's spectra (`_calibrations.SPECTRA`):
#: `conelum.spectrum_cone_luminance(nm, spd, 'macaque_equal')` under colour-science 0.4.7,
#: computed 2026-11-07, **on colour's 1 nm Stockman-Sharpe 2° table**, which this repository
#: bundled until it took the CIE's own 5 nm one the same day. It resamples a spectrum onto a 1 nm
#: grid over 390-780 nm by straight lines and sums.
WL_STYLE_LM = {"red": 0.25938029018247299, "green": 1.3150128100346472,
               "blue": 0.035432532839463377}


def colorset() -> "photometry.ColorSet":
    return photometry.ColorSet.load(FIXTURE)


def _srgb_light(hex_: str) -> tuple[float, float, float]:
    """The light the sRGB standard shows for an 8-bit color, CIE XYZ in cd/m²."""
    weights = [photometry._srgb_fraction(int(hex_[i:i + 2], 16) / 255) for i in (1, 3, 5)]
    primaries = [photometry.to_xyz(p) for p in (SRGB.red, SRGB.green, SRGB.blue)]
    return tuple(sum(w * p[k] for w, p in zip(weights, primaries)) for k in range(3))


def _spectrum(drive, panel) -> tuple:
    """The spectrum a panel whose transfer is a straight line shows at these output levels."""
    s = panel.spectra
    return tuple(sum(d * v for d, v in zip(drive, at)) for at in zip(s.red, s.green, s.blue))


def _macaque(drive, panel) -> float:
    return cones.macaque_luminance((NM, _spectrum(drive, panel)))


def _trial(lights: dict, params=()) -> Trial:
    """Each light a 1° disc on a ring at 4°, on the default black background."""
    at = iter([(4.0, 0.0), (0.0, 4.0), (-4.0, 0.0), (0.0, -4.0)])
    first = next(iter(lights))
    return Trial(
        start="on",
        params=list(params),
        windows=[Window("w", at=(4.0, 0.0), radius=1.0, on=first)],
        states=[State("on", enter=[Show(Stimulus(name, at=next(at), looks=Disc(size=1.0, color=light)))
                                   for name, light in lights.items()],
                      go=[On(After(1.0), Outcome.ABORT)])],
    )


def _four(cs) -> Trial:
    return _trial({name: photometry.ColorSetLight(cs, name) for name in COLORS})


#: A green primary nearer white than the measured test panel's: its gamut stops short of the set's
#: green (and, at 15 cd/m², of its blue).
NARROW_GREEN = xyY(0.30, 0.45, 140.0)


def test_macaque_luminance_of_d65_matches_wl_style_gray_ratio():
    """On the sRGB standard, through wl-style's model of its primaries: a D65 light's macaque
    luminance is its own cd/m², and each of wl-style's four previews is within 0.6% of its gray,
    as its CSV holds them equal (the previews are 8-bit roundings: the blue is 0.39% below on
    wl-style's own model, computed 2026-11-07). CIE Y is not what is held: the blue is 7% darker."""
    gray = _srgb_light(GRAY)
    assert photometry.macaque_cd_m2(gray, SRGB) == pytest.approx(gray[1], rel=1e-9)
    assert photometry.macaque_cd_m2(photometry.to_xyz(xyY(*D65, 15.0)), SRGB) == pytest.approx(15.0)
    for name, hex_ in PREVIEWS.items():
        ratio = photometry.macaque_cd_m2(_srgb_light(hex_), SRGB) / photometry.macaque_cd_m2(gray, SRGB)
        assert ratio == pytest.approx(1.0, abs=0.006), name
    assert _srgb_light(PREVIEWS["blue"])[1] / gray[1] < 0.94


def test_color_set_lights_are_equal_in_macaque_luminance_on_a_measured_calibration():
    """Through the panel's own spectra, each realized light's L + M is a D65 light's at 15 cd/m²
    on the same panel, to 0.1%, and its chromaticity is the set's: this panel shows all four."""
    panel = measured()
    cs = colorset()
    realized = photometry.realize(cs, panel)
    held = _macaque(panel.weights(xyY(*D65, 15.0)), panel)

    assert realized.desaturation == 0.0
    for name in COLORS:
        assert _macaque(realized.drive[name], panel) == pytest.approx(held, rel=1e-3), name
        X, Y, Z = realized.xyz[name]
        assert (X / (X + Y + Z), Y / (X + Y + Z)) == pytest.approx(cs.colors[name], abs=1e-9), name
    assert len({round(realized.xyz[name][1], 3) for name in COLORS}) == 4  # unequal in CIE Y


def test_a_short_gamut_desaturates_all_four_together_and_warns():
    """Review focus 3: every color moves toward the apex in xy by the one fraction, the smallest
    that fits them all (one of them at the gamut's edge), at the same macaque luminance; one
    warning, in every session kind, says by how much."""
    panel = measured(green=NARROW_GREEN)
    cs = colorset()
    realized = photometry.realize(cs, panel)
    d = realized.desaturation
    held = _macaque(panel.weights(xyY(*D65, 15.0)), panel)

    assert 0.0 < d < 1.0
    edge = []
    for name in COLORS:
        (x, y), (ax, ay) = cs.colors[name], cs.apex
        assert realized.xy[name] == pytest.approx((x + d * (ax - x), y + d * (ay - y)), abs=1e-9), name
        assert _macaque(realized.drive[name], panel) == pytest.approx(held, rel=1e-3), name
        weights = panel.weights_of(realized.xyz[name])
        assert all(-1e-6 <= w <= 1.0 + 1e-6 for w in weights), name
        edge.append(min(abs(w) for w in weights) < 1e-6)
    assert any(edge)

    found = [f for f in check(_four(cs), calibration=panel) if f.code == "color-set-desaturated"]
    assert len(found) == 1
    assert not found[0].blocking and found[0].accepted_in == SESSION_KINDS
    assert f"{100 * d:.1f}%" in found[0].detail and "isohue" in found[0].detail
    assert not [f for f in check(_four(cs), calibration=panel) if f.blocking]


def test_the_default_calibration_runs_with_its_model():
    """No spectra: the sRGB standard's macaque luminance is wl-style's model of its primaries.
    All four fit at 15 cd/m², and the task loads with the default's own warning, which says so."""
    cs = colorset()
    realized = photometry.realize(cs, SRGB)

    assert realized.desaturation == 0.0
    for name in COLORS:
        assert photometry.macaque_cd_m2(realized.xyz[name], SRGB) == pytest.approx(15.0, rel=1e-9)
        assert realized.xy[name] == pytest.approx(cs.colors[name], abs=1e-12)
        assert all(0.0 <= level <= 1.0 for level in realized.drive[name])
    found = {f.code: f for f in check(_four(cs), calibration=SRGB)}
    assert not [f for f in found.values() if f.blocking]
    assert "color-set-desaturated" not in found and "unrealizable-color" not in found
    assert "wl-style's model of the sRGB primaries" in found["color-on-default"].detail


def test_a_color_set_light_is_allowed_on_black():
    """An absolute light, not a contrast about the background: no `cone-color-on-black`."""
    found = check(_four(colorset()), calibration=measured())

    assert "cone-color-on-black" not in {f.code for f in found}
    assert not [f for f in found if f.blocking]


def test_a_calibration_measured_without_spectra_holds_the_set_through_the_defaults_model():
    """As cone colors convert there (XC-352's E3), with a warning naming what was assumed."""
    panel = measured(spectra=None)
    realized = photometry.realize(colorset(), panel)
    found = {f.code: f for f in check(_four(colorset()), calibration=panel)}

    for name in COLORS:
        assert photometry.macaque_cd_m2(realized.xyz[name], panel) == pytest.approx(15.0)
    assert found["color-set-without-spectra"].accepted_in == SESSION_KINDS
    assert "wl-style's model of the sRGB primaries" in found["color-set-without-spectra"].detail


def test_the_2deg_table_is_the_cies_own_and_a_changed_one_is_refused(monkeypatch):
    """The CIE 2006 2° cone fundamentals (DOI 10.25039/CIE.DS.tijidesg), bundled unmodified: its
    sha256 is its metadata's, it is read as the 10° table is -- the S cone's NaN beyond 615 nm read
    as zero -- and a table whose checksum is not the CIE's is refused (`cones.cie_file`)."""
    raw = resources.files("wl_xcon").joinpath("cie", cones.TABLE_2DEG).read_bytes()
    metadata = json.loads(resources.files("wl_xcon").joinpath(
        "cie", cones.TABLE_2DEG + "_metadata.json").read_text(encoding="utf-8"))
    t = cones.table_2deg()

    assert cones.TABLE_2DEG == "CIE_lms_cf_2deg.csv"
    sha256 = [c["checksum"] for c in metadata["checksums"] if c["hashMethod"] == "sha256"]
    assert hashlib.sha256(raw).hexdigest() == TABLE_2DEG_SHA256 == cones.CIE_FILES[
        cones.TABLE_2DEG] == sha256[0]
    assert metadata["identifier"]["identifier"] == "10.25039/CIE.DS.tijidesg"
    assert metadata["rightsList"][0]["rightsIdentifier"] == "CC BY-SA 4.0"
    assert (metadata["datatableInfo"]["interpolationMethod"],
            metadata["datatableInfo"]["extrapolationMethod"]) == ("linear", "zero")
    assert t.shape == (89, 4) and (t[0, 0], t[-1, 0]) == (390.0, 830.0)
    assert set(np.diff(t[:, 0])) == {5.0}
    assert not np.isnan(t).any() and (t[t[:, 0] > 615, 3] == 0.0).all()
    assert (t[t[:, 0] <= 615, 3] > 0.0).all()
    # Energy units, each peaking at 1 between its rows: 1 and 0.9971948 at its 5 nm rows (L at
    # 570 nm, M at 545 nm).
    assert t[:, 1].max() == 1.0 and t[:, 2].max() == pytest.approx(1.0, abs=3e-3)
    monkeypatch.setitem(cones.CIE_FILES, cones.TABLE_2DEG, "0" * 64)
    with pytest.raises(ValueError, match="is not the CIE's file"):
        cones.cie_file(cones.TABLE_2DEG)


def test_macaque_luminance_of_a_spectrum_is_l_plus_m_on_the_2deg_table_as_wl_style_computes_it():
    """L and M weighed 1:1, over the light's own wavelengths by the trapezoid rule (COL-35's rule
    for a measured spectrum); and given the samples wl-style integrates -- each of the tests' three
    spectra resampled onto its 1 nm grid -- wl-style's own numbers, **to 0.4%**: wl-style computed
    them on colour-science's 1 nm Stockman-Sharpe 2° table, and the CIE's 5 nm one, read by straight
    lines between its rows, moves these narrow bands by up to 0.31% on that grid (red +0.16%, green
    -0.12%, blue +0.31%; computed 2026-11-07). On the spectra as sampled, every 5 nm, the two
    tables agree within 1e-6 (8.4e-7 at most, computed the same day), so the rig's own reading of
    a measured panel is the table's, not the grid's."""
    t = cones.table_2deg()
    nm = np.arange(500.0, 601.0, 5.0)
    rows = t[(t[:, 0] >= 500) & (t[:, 0] <= 600)]
    lm = rows[:, 1] + rows[:, 2]
    grid = np.arange(390.0, 781.0, 1.0)

    assert cones.macaque_luminance((nm, np.full(nm.shape, 2.0))) == pytest.approx(
        2.0 * 5.0 * (lm.sum() - (lm[0] + lm[-1]) / 2), rel=1e-12)
    for channel, expected in WL_STYLE_LM.items():
        resampled = np.interp(grid, NM, getattr(SPECTRA, channel), left=0.0, right=0.0)
        assert cones.macaque_luminance((grid, resampled)) == pytest.approx(
            expected, rel=4e-3), channel


def test_a_color_set_is_read_from_its_plain_data_file_and_nothing_is_filled_in(tmp_path):
    cs = colorset()

    assert cs.name == "isohue" and tuple(cs.colors) == COLORS
    assert cs.colors["green"] == (0.31324, 0.50711) and cs.apex == (0.31272, 0.329)
    assert (cs.luminance_cd_m2, cs.held) == (15.0, "macaque_2deg_LM1")
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for broken, said in (
        ({k: v for k, v in data.items() if k != "apex"}, "no apex"),
        ({**data, "hue": 260}, "hue"),
        ({**data, "held": "cie_1931_Y"}, "macaque_2deg_LM1"),
        ({**data, "colors": {**data["colors"], "red": [0.7, 0.4]}}, "red"),
        ({**data, "luminance_cd_m2": 0}, "luminance"),
    ):
        path = tmp_path / "set.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(ValueError, match=said):
            photometry.ColorSet.load(path)
    with pytest.raises(ValueError, match="'violet'"):
        photometry.ColorSetLight(cs, "violet")
    # A task holding one has content a run can hash (XC-288 §4.4): its colors are plain text-keyed
    # data, as `declarations.canonical` reads them.
    written = canonical(photometry.ColorSetLight(cs, "red"))["fields"]["colorset"]["fields"]
    assert written["colors"]["red"] == [0.45955, 0.32918] and "luminance_cd_m2" not in written


def test_the_screen_draws_a_color_set_light_at_its_fraction_of_the_realized_light():
    from _rig import DIRECT
    from wl_xcon import screen

    cs = colorset()
    trial = _trial({"red": photometry.ColorSetLight(cs, "red", P("fade"))},
                   params=[Param("fade", unit="fraction", low=0.0, high=1.0)])
    stimulus = trial.states[0].enter[0].stimulus
    drawn = screen.resolve({"red": stimulus}, {"fade": 0.4}, trial, DIRECT, frame_period=1 / 240,
                           calibration=SRGB)

    assert drawn.items[0].fill.xyz == pytest.approx(
        tuple(0.4 * v for v in photometry.realize(cs, SRGB).xyz["red"]), rel=1e-12)



def _task(trial: Trial):
    """A task of the one structure `trial`, its reaction time and choice declared."""
    from wl_xcon.task import NO_CHOICE, ReactionTime, Task

    return Task(structures={"t": trial}, default="t", choice=NO_CHOICE,
                reaction_time=ReactionTime(state="on", to=(Outcome.ABORT,), note="n"))


def test_two_color_sets_of_one_name_are_refused_since_the_record_names_a_set_by_name():
    """**The record names a color-set light's set by its name** (`record._written`; the pop-out
    search build's final fixes, 1), each run's start row defining each set once (`color_sets`), so a
    task declaring two different sets of one name -- here the set and a dimmer copy -- writes lines
    no reader could tell apart: the load check refuses it, `color-set-named-twice`, naming the
    set. One set read twice from its file is one set."""
    from dataclasses import replace

    from wl_xcon.check import check_task

    def task(first, second):
        return _task(_trial({"a": photometry.ColorSetLight(first, "blue"),
                             "b": photometry.ColorSetLight(second, "red")}))

    twice = [f for f in check_task(task(colorset(), replace(colorset(), luminance_cd_m2=10.0)))
             if f.code == "color-set-named-twice"]
    assert len(twice) == 1 and twice[0].blocking, twice
    assert "'isohue'" in twice[0].detail
    assert "color-set-named-twice" not in {
        f.code for f in check_task(task(colorset(), colorset()))}


def test_a_runs_start_row_defines_each_set_as_written_and_as_this_panel_draws_it():
    """**What each run's start row defines once** (`taskd._color_sets`, its `color_sets`; the
    pop-out search build's final fixes, 1): each set the task declares, by name, as its file reads
    -- the colors as written -- and `realized` as this panel draws it, the screen's own, **one
    realization for each luminance the run's values draw the set at** (the fix round: the
    luminance a setting), each naming its luminance: on a panel that cannot show the set as
    written, the share of chroma every color gave up, each color as shown, moved toward the apex,
    and its output levels. A light naming a setting draws the set at the setting's value; one
    naming none, at the set's own. `None` for a task with no set."""
    from wl_xcon.taskd import _color_sets

    panel = measured(green=NARROW_GREEN)
    cs = colorset()
    shown = photometry.realize(cs, panel)
    assert shown.desaturation > 0.0

    def realization(shown) -> dict:
        return {"luminance_cd_m2": shown.luminance, "desaturation": shown.desaturation,
                "xy": {name: list(xy) for name, xy in shown.xy.items()},
                "xyz": {name: list(xyz) for name, xyz in shown.xyz.items()},
                "drive": {name: list(levels) for name, levels in shown.drive.items()},
                "macaque_row": list(photometry.macaque_row(panel))}

    defined = _color_sets(_task(_four(cs)), panel, {})

    assert defined == {"isohue": {
        "name": "isohue", "colors": {name: list(xy) for name, xy in cs.colors.items()},
        "apex": list(cs.apex), "luminance_cd_m2": 15.0, "held": "macaque_2deg_LM1",
        "source": cs.source, "design": None, "realized": [realization(shown)],
    }}
    assert defined["isohue"]["realized"][0]["xy"]["green"] != defined["isohue"]["colors"]["green"]
    dimmer = _trial({name: photometry.ColorSetLight(cs, name, luminance=P("bright"))
                     for name in COLORS},
                    params=[Param("bright", unit="cd/m2", low=1.0, high=30.0, start=15.0)])
    at_ten = _color_sets(_task(dimmer), panel, {"bright": 10.0})["isohue"]["realized"]
    assert at_ten == [realization(photometry.realize(cs, panel, 10.0))]
    assert at_ten[0]["luminance_cd_m2"] == 10.0
    assert _color_sets(_task(_trial({"a": xyY(0.3, 0.3, 10.0)})), panel, {}) is None


def test_a_lights_luminance_may_be_a_setting_realized_once_for_each_value():
    """The fix round (the PI, 2026-11-07: "everything should be adjustable in the console"): a
    color-set light's luminance at full may be a setting (`ColorSetLight.luminance`), bound where
    the screen binds its fraction; the set is realized once for each value on each panel and kept
    (`photometry.realized`), so no frame realizes it again; through the panel's own spectra each
    light at 10 cd/m² matches a D65 light's macaque luminance at 10; and one naming none is drawn at
    its set's own luminance."""
    from wl_xcon.screen import _Lights

    panel = measured()
    cs = colorset()
    named = photometry.ColorSetLight(cs, "blue", luminance=P("bright"))
    lights = _Lights(values={"bright": 10.0}, calibration=panel, background=None)

    at_ten = photometry.realized(cs, panel, 10.0)
    assert photometry.realized(cs, panel, 10.0) is at_ten
    assert photometry.realized(cs, panel, 15.0) is photometry.realized(cs, panel)
    assert at_ten.luminance == 10.0 and at_ten is not photometry.realized(cs, panel)
    assert lights.xyz(named) == pytest.approx(at_ten.xyz["blue"], rel=1e-12)
    assert photometry.macaque_cd_m2(lights.xyz(named), panel) == pytest.approx(10.0)
    assert _macaque(at_ten.drive["blue"], panel) == pytest.approx(
        _macaque(panel.weights(xyY(*D65, 10.0)), panel), rel=1e-3)
    plain = photometry.ColorSetLight(cs, "blue")
    assert lights.xyz(plain) == pytest.approx(photometry.realized(cs, panel).xyz["blue"])
    with pytest.raises(ValueError, match="above 0"):
        photometry.ColorSetLight(cs, "blue", luminance=0.0).at()


def test_a_luminance_range_that_desaturates_the_set_is_a_warning_saying_which_part():
    """The fix round: a luminance a setting gives is checked over its whole range at load. **A
    value that would desaturate the set is a warning, never a refusal** (the PI's "warnings over
    refusals", 2026-10-11; `color-set-desaturated`), saying which part of the range does -- here
    above about 26 cd/m² of 1 to 30 on the sRGB standard, 13.3% of chroma given up at 30 -- and a
    panel that shows the set over the whole range says nothing."""
    cs = colorset()
    bright = Param("bright", unit="cd/m2", low=1.0, high=30.0, start=15.0)
    trial = _trial({name: photometry.ColorSetLight(cs, name, luminance=P("bright"))
                    for name in COLORS}, params=[bright])

    on_default = {f.code: f for f in check(trial, calibration=SRGB)}
    on_measured = {f.code: f for f in check(trial, calibration=measured())}

    pale = on_default["color-set-desaturated"]
    assert pale.is_warning and pale.accepted_in == SESSION_KINDS
    assert ("as written above about 26 cd/m², of the 1 to 30 cd/m² setting 'bright' allows"
            in pale.detail)
    assert "13.3% at 30 cd/m²" in pale.detail
    assert not [f for f in on_default.values() if f.blocking]
    assert "color-set-desaturated" not in on_measured
    always = _trial({name: photometry.ColorSetLight(cs, name, luminance=P("bright"))
                     for name in COLORS},
                    params=[Param("bright", unit="cd/m2", low=40.0, high=50.0, start=45.0)])
    (every,) = [f for f in check(always, calibration=SRGB) if f.code == "color-set-desaturated"]
    assert "at any luminance setting 'bright' allows, 40 to 50 cd/m²" in every.detail



# --- A light's saturation (the console settings design's §6) ----------------------------------


def _xy(xyz) -> tuple[float, float]:
    X, Y, Z = xyz
    return (X / (X + Y + Z), Y / (X + Y + Z))


#: **Read independently of `photometry`, from `cam16` alone**: the lightness of the set's design
#: frame's gray (the generator's J' 65, isohue's own), its macaque luminance on the sRGB standard's
#: model, and a bisection's count for a chromaticity's light at a J'.
GRAY_J, HALVINGS = 65.0, 80


def _frame_gray() -> float:
    from wl_xcon import cam16

    return sum(r * v for r, v in zip(photometry.SRGB_MACAQUE, cam16.from_ucs((GRAY_J, 0.0, 0.0))))


def _unit(xy) -> tuple[float, float, float]:
    x, y = xy
    return (x / y, 1.0, (1.0 - x - y) / y)


def _ucs_at(xy, lightness: float) -> tuple[float, float, float]:
    """The CAM16-UCS J', a', b' of the light of chromaticity `xy` whose J' is `lightness`."""
    from wl_xcon import cam16

    low, high = 0.0, 4.0
    for _ in range(HALVINGS):
        middle = (low + high) / 2
        J = cam16.to_ucs(tuple(middle * u for u in _unit(xy)))[0]
        low, high = (middle, high) if J < lightness else (low, middle)
    return cam16.to_ucs(tuple(low * u for u in _unit(xy)))


def _color_ucs(xy) -> tuple[float, float, float]:
    """A color's CAM16-UCS J', a', b' in the design frame: held at the frame's gray's macaque
    luminance on the sRGB standard's model."""
    from wl_xcon import cam16

    unit = _unit(xy)
    per = sum(r * u for r, u in zip(photometry.SRGB_MACAQUE, unit))
    return cam16.to_ucs(tuple(u * _frame_gray() / per for u in unit))


def test_saturation_scales_a_lights_cam16_chroma_at_its_hue_holding_its_macaque_luminance():
    """The PI, 2026-11-18 (COL-39): "saturation scales the color's CAM16 chroma at a fixed hue,
    matching your generator". On the standard and on a panel that desaturates the set, each color's
    light at saturation 0.5, read in CAM16-UCS at its color's J' about the apex taken at that J',
    has half its color's chroma, to 1e-9, at its color's hue angle, to 1e-7°; at 1 it is its color
    as the set is realized, exactly; at 0 the apex, exactly; and a saturation a hair inside either
    end lies within 1e-7 of it, so the exact ends are the formula's own. At each its macaque
    luminance is its fraction of the set's, within 1e-9. The screen binds a saturation setting as
    it binds a fraction."""
    import math

    from wl_xcon.screen import _Lights

    cs = colorset()
    for panel in (SRGB, measured(green=NARROW_GREEN)):
        shown = photometry.realize(cs, panel)
        for color in COLORS:
            realized = shown.xy[color]
            J, a, b = _color_ucs(realized)
            _, a0, b0 = _ucs_at(cs.apex, J)
            for s in (0.0, 1e-9, 0.5, 1.0 - 1e-9, 1.0):
                light = photometry.ColorSetLight(cs, color, fraction=0.8, saturation=s)
                xyz = photometry.colorset_xyz(light, panel)
                xy, share = photometry.colorset_xy(light, panel)
                assert share == 0.0 and _xy(xyz) == pytest.approx(xy, abs=1e-12)
                assert photometry.macaque_cd_m2(xyz, panel) == pytest.approx(0.8 * 15.0, abs=1e-9)
                if s in (0.0, 1.0):
                    assert xy == (tuple(cs.apex) if s == 0.0 else realized), (panel.id, color, s)
                elif s < 0.5 or s > 0.5:
                    assert xy == pytest.approx(cs.apex if s < 0.5 else realized, abs=1e-7)
                else:
                    _, a_s, b_s = _ucs_at(xy, J)
                    assert math.hypot(a_s - a0, b_s - b0) == pytest.approx(
                        0.5 * math.hypot(a - a0, b - b0), abs=1e-9), (panel.id, color)
                    assert math.degrees(math.atan2(b_s - b0, a_s - a0)) == pytest.approx(
                        math.degrees(math.atan2(b - b0, a - a0)), abs=1e-7), (panel.id, color)
    lights = _Lights(values={"pale": 0.5}, calibration=SRGB, background=None)
    assert lights.xyz(photometry.ColorSetLight(cs, "red", saturation=P("pale"))) == pytest.approx(
        photometry.colorset_xyz(photometry.ColorSetLight(cs, "red", saturation=0.5), SRGB),
        rel=1e-12)
    with pytest.raises(ValueError, match="0 to 1"):
        photometry.colorset_xyz(photometry.ColorSetLight(cs, "red", saturation=1.5), SRGB)


def test_saturation_is_no_straight_line_in_xy_and_a_set_without_a_design_reads_the_generators_gray():
    """**Not the old line in xy**: isohue's red at saturation 0.5 lies off the straight segment
    from the apex to it, by more than 1e-3 in y (a CAM16-UCS hue line bends in xy). **A set with a
    design reads its own gray lightness**: isohue with its design (J' 65) gives the same light as
    the copy without one, which reads the generator's J' 65 (`photometry.GRAY_LIGHTNESS`); a design
    at J' 50 gives another."""
    import dataclasses

    cs = colorset()
    (ax, ay), (rx, ry) = cs.apex, cs.colors["red"]
    xy, _ = photometry.colorset_xy(photometry.ColorSetLight(cs, "red", saturation=0.5), SRGB)
    assert abs(xy[1] - (ay + 0.5 * (ry - ay))) > 1e-3
    designed = dataclasses.replace(cs, design={"space": "CAM16-UCS", "gray_lightness": 65.0,
                                               "chroma": 29.49})
    darker = dataclasses.replace(cs, design={"space": "CAM16-UCS", "gray_lightness": 50.0,
                                             "chroma": 29.49})
    assert photometry.GRAY_LIGHTNESS == 65.0
    at = {}
    for name, each in (("plain", cs), ("designed", designed), ("darker", darker)):
        at[name], _ = photometry.colorset_xy(
            photometry.ColorSetLight(each, "red", saturation=0.5), SRGB)
    assert at["designed"] == at["plain"]
    assert abs(at["darker"][0] - at["plain"][0]) > 1e-6


def test_every_saturation_of_isohue_is_shown_on_the_standard_and_the_test_panels():
    """**No isohue light leaves these panels' gamuts at any saturation**: on the standard and on a
    narrow test panel, at luminances the set is shown at as written and desaturated, every
    saturation on a grid from 0 to 1 is a light the panel makes, none clipped, none moved
    (`colorset_xy`'s share 0), each at its CAM16-UCS place (`saturated_xy`) -- what the
    ColorSetLight's docstring says was computed."""
    cs = colorset()
    for panel, luminances in ((SRGB, (5.0, 15.0, 30.0)), (measured(green=NARROW_GREEN), (15.0,))):
        for luminance in luminances:
            assert photometry.unrealizable(
                photometry.ColorSetLight(cs, "green", luminance=luminance), panel) is None
            shown = photometry.realize(cs, panel, luminance)
            for color in COLORS:
                for step in range(21):
                    s = step / 20
                    light = photometry.ColorSetLight(cs, color, luminance=luminance, saturation=s)
                    assert photometry.unrealizable(light, panel) is None, (
                        panel.id, luminance, color, step)
                    xy, share = photometry.colorset_xy(light, panel)
                    assert share == 0.0
                    assert xy == photometry.saturated_xy(cs, shown.xy[color], s)


#: **A panel built so a CAM16-UCS path leaves its gamut**: its red and green primaries on the line
#: y = 0.3295, just above isohue's apex (y 0.32900) and its red (y 0.32918), so the straight segment
#: between them is inside, and the red's path at saturation 0.5, which bows to y 0.3307, is not.
#: Illustrative, as every test panel is.
EDGE = 0.3295


def test_a_saturation_outside_the_panels_gamut_is_moved_toward_the_apex_and_warned():
    """**Handled as the realization handles a light outside the gamut**: a set of isohue's red
    alone, shown as written on a panel whose edge runs between its straight segment and its
    CAM16-UCS path, is drawn at saturation 0.5 moved toward the apex in xy by the least share that
    shows it (to `DESATURATION_STEP`), on the line from its CAM16-UCS place to the apex, its
    luminance held and nothing clipped; the load check warns `color-set-desaturated`, naming the
    light, its saturation and the share -- reading a saturation setting's range between its ends,
    where its ends need nothing -- and on the standard it warns nothing."""
    one = photometry.ColorSet(name="red", colors={"red": colorset().colors["red"]},
                              apex=colorset().apex, luminance_cd_m2=2.0, held=colorset().held,
                              source="a test's")
    panel = measured(red=xyY(0.66, EDGE, 45.0), green=xyY(0.05, EDGE, 140.0),
                     blue=xyY(0.15, 0.06, 12.0))
    shown = photometry.realize(one, panel)
    assert shown.desaturation == 0.0
    light = photometry.ColorSetLight(one, "red", saturation=0.5)
    asked = photometry.saturated_xy(one, shown.xy["red"], 0.5)
    xy, share = photometry.colorset_xy(light, panel)
    assert 0.5 < share < 0.9
    (ax, ay) = one.apex
    assert xy == pytest.approx((asked[0] + share * (ax - asked[0]),
                                asked[1] + share * (ay - asked[1])), abs=1e-12)
    assert photometry.unrealizable(light, panel) is None
    narrower = (asked[0] + (share - 1e-6) * (ax - asked[0]),
                asked[1] + (share - 1e-6) * (ay - asked[1]))
    weights = panel.weights_of(photometry._held_light(narrower, 2.0, panel))
    assert max(weights) > 1.0 + photometry.TOLERANCE or min(weights) < -photometry.TOLERANCE
    xyz = photometry.colorset_xyz(light, panel)
    assert _xy(xyz) == pytest.approx(xy, abs=1e-12)
    assert photometry.macaque_cd_m2(xyz, panel) == pytest.approx(2.0, abs=1e-9)
    for s in (0.0, 1.0):
        assert photometry.colorset_xy(
            photometry.ColorSetLight(one, "red", saturation=s), panel)[1] == 0.0

    pale = Param("pale", unit="fraction", low=0.0, high=1.0, start=1.0)
    lit = {"odd": photometry.ColorSetLight(one, "red", saturation=P("pale"))}
    (warned,) = [f for f in check(_trial(lit, params=[pale]), calibration=panel)
                 if f.code == "color-set-desaturated"]
    assert not warned.blocking and warned.accepted_in == SESSION_KINDS
    assert warned.subjects == ("color set 'red'",)
    assert "CAM16-UCS" in warned.detail
    assert re.search(r"Disc in red at saturation 0\.\d+ and 2 cd/m², by \d+\.\d%$", warned.detail), (
        warned.detail)
    assert [f for f in check(_trial(lit, params=[pale]), calibration=SRGB)
            if f.code == "color-set-desaturated"] == []


def test_a_swatch_is_the_light_as_the_srgb_standard_shows_it():
    """`photometry.srgb_hex`: the standard's white at its 80 cd/m² is `#ffffff`, black `#000000`,
    wl-style's four previews and its gray read back as themselves, and a light past the gamut is
    clipped to a color the page can show."""
    assert photometry.srgb_hex(photometry.to_xyz(xyY(*D65, 80.0))) == "#ffffff"
    assert photometry.srgb_hex((0.0, 0.0, 0.0)) == "#000000"
    for hex_ in (*PREVIEWS.values(), GRAY):
        assert photometry.srgb_hex(_srgb_light(hex_)) == hex_
    bright = photometry.srgb_hex(photometry.to_xyz(xyY(0.15, 0.06, 500.0)))
    assert len(bright) == 7 and bright.startswith("#")


def test_a_light_at_saturation_zero_adds_no_desaturation_warning():
    """The pop-out revision's seam, defect 1: a light is read at its own saturation. Beside the
    four colors at 15 cd/m², a fixation light at saturation 0 drawn at a luminance setting of 1 to
    30 cd/m² -- where the standard cannot show the set as written above about 26 -- is the set's
    gray whatever its hue, so it adds no `color-set-desaturated`; at saturation 1 the same light
    is warned for it."""
    cs = colorset()
    bright = Param("bright", unit="cd/m2", low=1.0, high=30.0, start=15.0)

    def warned(saturation: float) -> list:
        lights = {name: photometry.ColorSetLight(cs, name) for name in COLORS[:3]}
        lights["fix"] = photometry.ColorSetLight(cs, "green", luminance=P("bright"),
                                                 saturation=saturation)
        return [f for f in check(_trial(lights, params=[bright]), calibration=SRGB)
                if f.code == "color-set-desaturated"]

    assert warned(0.0) == []
    (pale,) = warned(1.0)
    assert "'bright'" in pale.detail
