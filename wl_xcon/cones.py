"""The cone fundamentals every cone color converts through (engine spec §7.9; engine build A2).

**One lab-wide observer: the CIE 2006 10° cone fundamentals**, Stockman and Sharpe's, unadjusted
for macaques (the PI, 2026-10-07 and 2026-10-08: A2's Q4, "Human 10°, switchable later"; COL-15,
COL-16). Its table is the CIE's own data set, bundled unmodified in `wl_xcon/cie/` under CC BY-SA
4.0 (A2's Q3, "Bundle the CIE's files"; ADR-0012), and **read only after its sha256 matches the one
the CIE's metadata gives**, so a table that changed on disk is refused rather than believed. Its
parameters are `CIE2006_10`'s, recorded with every session that converts a cone color
(`Observer.record`), so a macaque lens or macular setting switched on later is told apart.

**Isoluminance and the DKL luminance axis are the CIE's cone-based V_F,10** (A2's Q5, "Cone-based
V(λ), 10°"; COL-17): `V_F10`, the luminance row of the CIE's transformation from these
fundamentals to XYZ_F,10 (`LMS_TO_XYZ_F10`), which `tests/test_cones.py` holds to the CIE's own
tabulated XYZ_F,10. cd/m² stays on CIE V(λ): nothing here names an absolute luminance.

Read when a calibration is converted, at load; never inside a frame.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib import resources

import numpy as np

#: The CIE's files this package carries, each by the sha256 its metadata JSON gives
#: (`checksums`, read 2026-10-09; the data set page's MD5 for the LMS table is stale, the
#: metadata's is not). `CIE_lms_cf_10deg.csv` is DOI 10.25039/CIE.DS.nxsqeri8 (CIE 170-1:2006,
#: Table 6.2); `CIE_cfb_stv_10deg.csv`, the XYZ_F,10 functions, is DOI 10.25039/CIE.DS.dm6qiig7
#: (CIE 170-2:2015, Table 10.8), carried so a test can hold `LMS_TO_XYZ_F10` to it.
CIE_FILES = {
    "CIE_lms_cf_10deg.csv": "bd64f1f688a4b319c6d3fa6b31770a32eaaaaea0eed532befd0424f96304db18",
    "CIE_cfb_stv_10deg.csv": "9019a35f8f51215e245f818e87d4251147d1925a8fbe9a49944fe7f011f16e38",
}

#: The cone fundamentals' table.
TABLE = "CIE_lms_cf_10deg.csv"

#: The CIE's transformation from the 10° cone fundamentals (energy, each peaking at 1) to its
#: cone-fundamental-based tristimulus functions XYZ_F,10, row by row: x̄_F,10, ȳ_F,10, z̄_F,10.
#: As printed in Stockman and Rider (2023), Eq. 15 (CC BY 4.0, read 2026-10-09 in its Europe PMC
#: full text, PMC10946592); CIE 170-2:2015 itself was not opened. Applied to the bundled table it
#: reproduces the CIE's tabulated XYZ_F,10 at every 5 nm wavelength within 1.4e-6 (computed
#: 2026-10-09; `tests/test_cones.py`).
LMS_TO_XYZ_F10 = (
    (1.93986443, -1.34664359, 0.43044935),
    (0.69283932, 0.34967567, 0.0),
    (0.0, 0.0, 2.14687945),
)

#: V_F,10, the CIE's cone-based luminosity for a 10° field: this many of L and of M, and no S
#: (A2's Q5). It is `LMS_TO_XYZ_F10`'s luminance row, and the CIE tabulates the same function
#: as its own data set (DOI 10.25039/CIE.DS.8mrru44q; `CIE_cfb_sle_10deg.csv`, 1 nm, 390-830 nm,
#: from CIE 170-2:2015, Table 10.4). Checked 2026-10-10 against that file (its sha256 is its
#: metadata's): equal to the ȳ_F,10 column of `CIE_cfb_stv_10deg.csv` at all 441 wavelengths
#: (difference 0), and within 4.5e-7 of `V_F10[0]*l̄10 + V_F10[1]*m̄10` at the 89 rows of the
#: bundled cone table. That file is not bundled.
V_F10 = (LMS_TO_XYZ_F10[1][0], LMS_TO_XYZ_F10[1][1])


@dataclass(frozen=True, slots=True)
class Observer:
    """Whose cones a cone color is in, and the parameters that make it that observer, recorded
    with each session (A2's Q4: "its parameters recorded").

    The densities are the CIE standard's for its field size, as Stockman and Rider (2023) state
    them ("Macular and lens optical density spectra"; "Formulae for standard observers"): the peak
    photopigment optical densities of the L, M and S cones, the macular pigment's density at
    460 nm and the lens's at 400 nm."""

    name: str
    #: The DOI of the table it is.
    data: str
    field_deg: float
    peak_optical_density: tuple[float, float, float]
    macular_density_460nm: float
    lens_density_400nm: float
    #: The luminosity function behind isoluminance and the DKL luminance axis, and its weights on
    #: the L and M fundamentals.
    luminosity: str
    luminosity_weights: tuple[float, float]
    #: How the table is read between its rows.
    interpolation: str

    def record(self) -> dict:
        """The observer as a session record writes it. The standard observer's age is not
        recorded: no source read for this build states it (the engine A2 plan's call 1)."""
        return {
            "name": self.name,
            "data": self.data,
            "field_deg": self.field_deg,
            "peak_optical_density": list(self.peak_optical_density),
            "macular_density_460nm": self.macular_density_460nm,
            "lens_density_400nm": self.lens_density_400nm,
            "luminosity": self.luminosity,
            "luminosity_weights": list(self.luminosity_weights),
            "interpolation": self.interpolation,
        }


#: **The lab's observer** (COL-15, COL-16): the CIE 2006 10° standard observer as published, its
#: lens and macular pigment the human standard's. A macaque setting, when the PI switches one on,
#: is a different `Observer` built from these parts (XC-301).
CIE2006_10 = Observer(
    name="CIE 2006 10°",
    data="10.25039/CIE.DS.nxsqeri8",
    field_deg=10.0,
    peak_optical_density=(0.38, 0.38, 0.30),
    macular_density_460nm=0.095,
    lens_density_400nm=1.7649,
    luminosity="V_F,10",
    luminosity_weights=V_F10,
    interpolation="linear between the table's 5 nm points; zero outside 390-830 nm",
)


def cie_file(name: str) -> bytes:
    """One of the CIE's bundled files, **refused unless its sha256 is the CIE's**: an edited, a
    truncated or a re-saved table (a spreadsheet's line endings) would convert every cone color
    wrongly, and nothing downstream could tell."""
    expected = CIE_FILES[name]
    raw = resources.files("wl_xcon").joinpath("cie", name).read_bytes()
    found = hashlib.sha256(raw).hexdigest()
    if found != expected:
        raise ValueError(
            f"wl_xcon/cie/{name} is not the CIE's file: its sha256 is {found}, and the CIE's "
            f"metadata gives {expected}; restore it from the package"
        )
    return raw


def parse(raw: bytes) -> np.ndarray:
    """A CIE table's rows as numbers, one row per wavelength. A blank the CIE leaves (the S cone
    beyond 615 nm, written NaN) is zero: its metadata's declared extrapolation."""
    rows = [line.split(",") for line in raw.decode("ascii").splitlines() if line.strip()]
    return np.nan_to_num(np.array([[float(v) for v in row] for row in rows]), nan=0.0)


_TABLE: list = []


def table() -> np.ndarray:
    """The 10° cone fundamentals, (89, 4): wavelength in nm, 390 to 830 by 5, then l̄10, m̄10 and
    s̄10, each in energy units peaking at 1. Read once, on first use."""
    if not _TABLE:
        _TABLE.append(parse(cie_file(TABLE)))
    return _TABLE[0]


def fundamentals(nm) -> np.ndarray:
    """l̄10, m̄10 and s̄10 at each wavelength in `nm`, (n, 3): **linear interpolation between the
    CIE's 5 nm values**, the method its metadata declares, and zero outside 390-830 nm, its
    declared extrapolation. Computed, never written: a resampled table would be an adaptation of
    the CIE's (ADR-0012)."""
    t = table()
    at = np.asarray(nm, dtype=float)
    return np.stack([np.interp(at, t[:, 0], t[:, k], left=0.0, right=0.0) for k in (1, 2, 3)],
                    axis=-1)


def excitations(nm, radiance) -> tuple[float, float, float]:
    """The L, M and S excitations of a light whose spectral radiance is `radiance` at each of
    `nm`: each fundamental times the radiance, integrated by the trapezoid rule over the
    light's own wavelengths. In the radiance's units times nm; only ratios are ever read."""
    at = np.asarray(nm, dtype=float)
    weighted = fundamentals(at) * np.asarray(radiance, dtype=float)[:, None]
    steps = np.diff(at)[:, None]
    totals = ((weighted[1:] + weighted[:-1]) / 2.0 * steps).sum(axis=0)
    return (float(totals[0]), float(totals[1]), float(totals[2]))
