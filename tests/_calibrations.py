"""The display calibrations the tests share (engine build B): a straight-line transfer and one
measured test panel, each written once rather than in every test file that builds one (the
engine B plan's pre-flight ruling D1/D2). **Illustrative: nobody measured this panel**; a real
calibration comes from a photometer and is committed under `docs/measurements/<rig>/`.

Never collected: its name does not start with `test_`.
"""

from __future__ import annotations

from wl_xcon.photometry import Calibration, Transfer, xyY

#: A straight-line transfer, as illustrative as every calibration built on it.
LINEAR = Transfer(levels=(0.0, 1.0), fractions=(0.0, 1.0))

#: The measured test panel's primaries and background, each x, y and Y in cd/m², as its JSON
#: record gives them (`photometry.read_calibration`), and whose luminous efficiency it states.
PRIMARIES = {"red": (0.68, 0.31, 45.0), "green": (0.26, 0.69, 140.0), "blue": (0.14, 0.05, 12.0)}
BACKGROUND = (0.3127, 0.329, 20.0)
OBSERVER = "CIE 1931 2°"


def measured(**over) -> Calibration:
    """The measured test panel, measured 2027-01-20, a straight-line transfer on each channel;
    each field given replaces its own."""
    fields = dict(
        red=xyY(*PRIMARIES["red"]),
        green=xyY(*PRIMARIES["green"]),
        blue=xyY(*PRIMARIES["blue"]),
        background=xyY(*BACKGROUND),
        transfer=(LINEAR,) * 3,
        observer=OBSERVER,
        measured_on="2027-01-20",
        id="rig1@2027-01-20",
    )
    fields.update(over)
    return Calibration(**fields)
