"""The cone fundamentals (engine spec §7.9; engine build A2): the CIE's own table, bundled and
checked by its checksum, and the CIE's transformation to XYZ_F,10, held to the CIE's own data."""

import fnmatch
import hashlib
import json
import tomllib
from importlib import resources
from pathlib import Path

import numpy as np
import pytest

from wl_xcon import cones

CIE = resources.files("wl_xcon").joinpath("cie")


def _metadata(name: str) -> dict:
    metadata = {"CIE_lms_cf_10deg.csv": "CIE_lms_cf_10deg.csv_metadata_v2.json",
                "CIE_cfb_stv_10deg.csv": "CIE_cfb_stv_10deg.csv_metadata.json"}[name]
    return json.loads(CIE.joinpath(metadata).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(cones.CIE_FILES))
def test_each_bundled_table_is_the_cies_file_by_its_metadatas_sha256(name):
    metadata = _metadata(name)
    given = {c["hashMethod"]: c["checksum"] for c in metadata["checksums"]}

    assert hashlib.sha256(CIE.joinpath(name).read_bytes()).hexdigest() == given["sha256"]
    assert cones.CIE_FILES[name] == given["sha256"]
    assert metadata["rightsList"][0]["rightsIdentifier"] == "CC BY-SA 4.0"
    assert metadata["alternateIdentifiers"][0]["alternateIdentifier"] == name


def test_a_table_whose_checksum_is_not_the_cies_is_refused(monkeypatch):
    monkeypatch.setitem(cones.CIE_FILES, cones.TABLE, "0" * 64)

    with pytest.raises(ValueError, match="is not the CIE's file"):
        cones.cie_file(cones.TABLE)


def test_the_table_passes_the_cies_own_validations():
    """The metadata's `validations`: the sum of each column, and its row 32, counted from 1
    (index 31, 545 nm)."""
    validations = {v["validationType"]: v
                   for v in _metadata(cones.TABLE)["datatableInfo"]["validations"]}
    t = cones.table()

    assert t.shape == (89, 4)
    assert (t[0, 0], t[-1, 0]) == (390.0, 830.0)
    assert t.sum(axis=0) == pytest.approx(
        json.loads(validations["sumOfColumns"]["validationValue"]), rel=1e-12)
    assert list(t[31]) == [float(v) for v in validations["sampleRow"]["validationValue"].split(",")]


def test_the_s_cone_is_zero_where_the_cie_leaves_it_blank():
    t = cones.table()

    assert (t[t[:, 0] > 615, 3] == 0.0).all()
    assert t[t[:, 0] == 615, 3][0] == pytest.approx(2.99354e-06)


def test_the_cies_transformation_reproduces_its_own_xyz_f10_at_every_tabulated_wavelength():
    """A2's Q2 rests on this matrix: printed by Stockman and Rider (2023), Eq. 15, and held here to
    the CIE's tabulated XYZ_F,10 (DOI 10.25039/CIE.DS.dm6qiig7) wherever the cone table has a row."""
    xyz_f10 = cones.parse(cones.cie_file("CIE_cfb_stv_10deg.csv"))
    t = cones.table()
    rows = np.searchsorted(xyz_f10[:, 0], t[:, 0])
    assert (xyz_f10[rows, 0] == t[:, 0]).all()

    computed = t[:, 1:] @ np.asarray(cones.LMS_TO_XYZ_F10).T

    assert np.abs(computed - xyz_f10[rows, 1:]).max() < 2e-6


def test_v_f10_is_the_luminance_row_and_has_no_s():
    assert cones.V_F10 == (0.69283932, 0.34967567)
    assert cones.LMS_TO_XYZ_F10[1][2] == 0.0


def test_fundamentals_are_the_table_at_its_wavelengths_and_linear_between():
    t = cones.table()

    assert np.array_equal(cones.fundamentals(t[:, 0]), t[:, 1:])
    middle = cones.fundamentals([547.5])[0]
    assert middle == pytest.approx((t[t[:, 0] == 545, 1:][0] + t[t[:, 0] == 550, 1:][0]) / 2)


def test_fundamentals_are_zero_outside_the_cies_range():
    assert cones.fundamentals([380.0, 389.9, 830.1, 900.0]).tolist() == [[0.0, 0.0, 0.0]] * 4


def test_excitations_integrate_each_fundamental_over_the_lights_own_wavelengths():
    """A flat light of 2 per nm over 500-600 nm, sampled every 5 nm, excites each cone by twice the
    trapezoid area under its fundamental there."""
    nm = np.arange(500.0, 601.0, 5.0)
    t = cones.table()
    inside = (t[:, 0] >= 500) & (t[:, 0] <= 600)
    expected = [2.0 * 5.0 * (t[inside, k].sum() - (t[inside, k][0] + t[inside, k][-1]) / 2)
                for k in (1, 2, 3)]

    assert cones.excitations(nm, np.full(nm.shape, 2.0)) == pytest.approx(expected, rel=1e-12)


def test_excitations_scale_with_the_light():
    nm = np.arange(400.0, 701.0, 1.0)
    light = np.exp(-0.5 * ((nm - 530.0) / 20.0) ** 2)

    once = np.asarray(cones.excitations(nm, light))
    assert np.asarray(cones.excitations(nm, 3.0 * light)) == pytest.approx(3.0 * once)
    assert once[1] > once[0] > once[2] > 0.0


def test_the_observer_records_its_parameters():
    assert cones.CIE2006_10.record() == {
        "name": "CIE 2006 10°",
        "data": "10.25039/CIE.DS.nxsqeri8",
        "field_deg": 10.0,
        "peak_optical_density": [0.38, 0.38, 0.30],
        "macular_density_460nm": 0.095,
        "lens_density_400nm": 1.7649,
        "luminosity": "V_F,10",
        "luminosity_weights": [0.69283932, 0.34967567],
        "interpolation": "linear between the table's 5 nm points; zero outside 390-830 nm",
    }


def test_the_cie_files_and_their_notice_are_found_through_the_package_and_ship_with_it():
    """Read through `importlib.resources`, as an installed package reads them,
    and every one covered by `pyproject.toml`'s package data; git keeps them byte for byte."""
    names = [*cones.CIE_FILES, "CIE_lms_cf_10deg.csv_metadata_v2.json",
             "CIE_cfb_stv_10deg.csv_metadata.json", "NOTICE.md"]
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["wl_xcon"]

    for name in names:
        assert CIE.joinpath(name).is_file(), name
        assert any(fnmatch.fnmatch(f"cie/{name}", pattern) for pattern in patterns), name
    assert "wl_xcon/cie/* -text" in (root / ".gitattributes").read_text(encoding="utf-8")
