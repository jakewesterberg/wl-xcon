"""The display calibrations the tests share (engine build B): a straight-line transfer and one
measured test panel, each written once rather than in every test file that builds one (the
engine B plan's pre-flight ruling D1/D2). **Illustrative: nobody measured this panel**; a real
calibration comes from a photometer and is committed under `docs/measurements/<rig>/`. And
`promptly`, for the tests of a record that is a named pipe.

Never collected: its name does not start with `test_`.
"""

from __future__ import annotations

import math
import os
import threading
from pathlib import Path

import pytest

from wl_xcon.photometry import Calibration, Spectra, Transfer, xyY

#: A straight-line transfer, as illustrative as every calibration built on it.
LINEAR = Transfer(levels=(0.0, 1.0), fractions=(0.0, 1.0))

#: The measured test panel's primaries and background, each x, y and Y in cd/m², as its JSON
#: record gives them (`photometry.read_calibration`), and whose luminous efficiency it states.
PRIMARIES = {"red": (0.68, 0.31, 45.0), "green": (0.26, 0.69, 140.0), "blue": (0.14, 0.05, 12.0)}
BACKGROUND = (0.3127, 0.329, 20.0)
OBSERVER = "CIE 1931 2°"

#: Where the measured test panel's spectra are sampled: every 5 nm from 380 to 780.
NM = tuple(float(nm) for nm in range(380, 781, 5))


def _band(center: float, width: float, peak: float) -> tuple:
    """A Gaussian band, `width` its full width at half maximum, nm (engine A2 research note §3's
    narrowband display model: 630/25, 530/25 and 455/20 nm)."""
    sigma = width / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    return tuple(peak * math.exp(-0.5 * ((nm - center) / sigma) ** 2) for nm in NM)


#: The measured test panel's spectra, W·sr⁻¹·m⁻²·nm⁻¹ at full drive. **Illustrative, and not
#: consistent with `PRIMARIES`' chromaticities**: nothing in this build checks the two against
#: each other (XC-308), and the tests need only some spectra.
SPECTRA = Spectra(nm=NM, red=_band(630.0, 25.0, 0.02), green=_band(530.0, 25.0, 0.03),
                  blue=_band(455.0, 20.0, 0.01))

#: Housekeeping, not a measurement: how long a read of a record that is a named pipe may take
#: before its test fails rather than waits.
PIPE_WAIT_S = 5.0


def measured(**over) -> Calibration:
    """The measured test panel, measured 2027-01-20, a straight-line transfer on each channel
    and `SPECTRA`; each field given replaces its own."""
    fields = dict(
        red=xyY(*PRIMARIES["red"]),
        green=xyY(*PRIMARIES["green"]),
        blue=xyY(*PRIMARIES["blue"]),
        background=xyY(*BACKGROUND),
        transfer=(LINEAR,) * 3,
        observer=OBSERVER,
        measured_on="2027-01-20",
        id="rig1@2027-01-20",
        spectra=SPECTRA,
    )
    fields.update(over)
    return Calibration(**fields)


def promptly(call, pipe: Path):
    """`call()`'s result, or what it raised, once it returns within `PIPE_WAIT_S` -- for a call
    that reads `pipe`, a named pipe with no writer (the engine B final review). One still
    waiting fails its test rather than hang the suite, and is released first: a writer opens
    `pipe` and closes it, so the open it waits in returns."""
    outcome: dict = {}

    def target() -> None:
        try:
            outcome["returned"] = call()
        except BaseException as error:  # noqa: BLE001 -- handed back to the test below
            outcome["raised"] = error

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(PIPE_WAIT_S)
    if thread.is_alive():
        try:
            os.close(os.open(pipe, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        thread.join(PIPE_WAIT_S)
        pytest.fail(f"still waiting on the named pipe {pipe} after {PIPE_WAIT_S:g} s")
    if "raised" in outcome:
        raise outcome["raised"]
    return outcome["returned"]
