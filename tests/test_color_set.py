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
    -- the colors as written -- and `realized` as this panel draws it, the screen's own: on a panel
    that cannot show the set as written, the share of chroma every color gave up, each color as
    shown, moved toward the apex, and its output levels. `None` for a task with no set."""
    from wl_xcon.taskd import _color_sets

    panel = measured(green=NARROW_GREEN)
    cs = colorset()
    shown = photometry.realize(cs, panel)
    assert shown.desaturation > 0.0

    defined = _color_sets(_task(_four(cs)), panel)

    assert defined == {"isohue": {
        "name": "isohue", "colors": {name: list(xy) for name, xy in cs.colors.items()},
        "apex": list(cs.apex), "luminance_cd_m2": 15.0, "held": "macaque_2deg_LM1",
        "source": cs.source,
        "realized": {"desaturation": shown.desaturation,
                     "xy": {name: list(xy) for name, xy in shown.xy.items()},
                     "drive": {name: list(levels) for name, levels in shown.drive.items()}},
    }}
    assert defined["isohue"]["realized"]["xy"]["green"] != defined["isohue"]["colors"]["green"]
    assert _color_sets(_task(_trial({"a": xyY(0.3, 0.3, 10.0)})), panel) is None
