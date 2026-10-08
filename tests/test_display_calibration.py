"""The display's color calibration as a record (engine spec §7, §12.6): the default is the sRGB
standard and says so; a measured one carries its id, its date and a measured transfer per
channel."""

import json
from datetime import date

import pytest

from _calibrations import BACKGROUND, LINEAR, OBSERVER, PRIMARIES, measured
from wl_xcon.photometry import (
    D65,
    DKL,
    SRGB,
    SRGB_TRANSFER,
    SRGB_WHITE_CD_M2,
    Transfer,
    read_calibration,
    unrealizable,
    xyY,
)


def _record(**over) -> dict:
    record = {
        "id": "rig1@2027-01-20",
        "measured_on": "2027-01-20",
        "observer": OBSERVER,
        "primaries": dict(PRIMARIES),
        "background": BACKGROUND,
        "transfer": {c: [[0.0, 0.0], [0.5, 0.2], [1.0, 1.0]] for c in ("red", "green", "blue")},
    }
    record.update(over)
    return record


def _write(folder, record, name="cal.json"):
    path = folder / name
    path.write_text(json.dumps(record))
    return path


def test_the_default_is_the_srgb_standard_and_says_so():
    assert (SRGB.standard, SRGB.id, SRGB.measured_on) == (True, "srgb-standard", "")
    assert SRGB.age_days(date(2027, 1, 20)) is None
    assert [(p.x, p.y) for p in (SRGB.red, SRGB.green, SRGB.blue)] == [
        (0.64, 0.33), (0.30, 0.60), (0.15, 0.06)]
    assert SRGB.max_cone_contrast is None


def test_full_drive_on_the_default_is_the_standards_white_and_no_brighter():
    assert SRGB_WHITE_CD_M2 == 80.0
    assert SRGB.weights(xyY(*D65, SRGB_WHITE_CD_M2)) == pytest.approx((1.0, 1.0, 1.0), abs=1e-12)
    assert unrealizable(xyY(*D65, SRGB_WHITE_CD_M2), SRGB) is None
    assert unrealizable(xyY(*D65, SRGB_WHITE_CD_M2 + 0.01), SRGB) is not None



def test_no_dkl_color_is_realizable_on_a_calibration_that_states_no_cone_contrast_limit():
    """The default states none, so even a faint DKL color is refused against it, by name,
    until build A2 converts DKL through cone fundamentals."""
    assert "states no cone-contrast limit" in unrealizable(DKL(l_m=0.01), SRGB)
    assert unrealizable(DKL(l_m=0.01), measured()) is None

def test_the_default_transfer_is_the_srgb_curve_at_ten_bits():
    assert SRGB.transfer == (SRGB_TRANSFER,) * 3
    assert len(SRGB_TRANSFER.levels) == 1024
    for code in (0, 1, 41, 42, 300, 512, 1000, 1023):
        level = code / 1023
        expected = level / 12.92 if level <= 0.04045 else ((level + 0.055) / 1.055) ** 2.4
        assert SRGB_TRANSFER.levels[code] == level
        assert SRGB_TRANSFER.fractions[code] == pytest.approx(expected, rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("levels, fractions, said", [
    ((0.0,), (0.0,), "at least two"),
    ((0.0, 1.0), (0.0, 0.5, 1.0), "at least two"),
    ((0.0, float("nan"), 1.0), (0.0, 0.5, 1.0), "finite"),
    ((0.0, 1.0), (0.0, True), "finite"),
    ((0.1, 1.0), (0.0, 1.0), "from level 0 to level 1"),
    ((0.0, 0.9), (0.0, 1.0), "from level 0 to level 1"),
    ((0.0, 0.5, 0.5, 1.0), (0.0, 0.2, 0.3, 1.0), "rise strictly"),
    ((0.0, 0.5, 0.7, 1.0), (0.0, 0.6, 0.4, 1.0), "never fall"),
    ((0.0, 1.0), (0.0, 0.9), "end at 1"),
    ((0.0, 1.0), (-0.1, 1.0), "start at 0 or above"),
    ([0.0, 1.0], (0.0, 1.0), "tuples"),
])
def test_a_transfer_is_a_measured_table_or_it_is_refused(levels, fractions, said):
    with pytest.raises(ValueError, match=said):
        Transfer(levels=levels, fractions=fractions)


def test_a_measured_calibration_carries_its_age_by_the_calendar():
    panel = measured()

    assert panel.age_days(date(2027, 1, 20)) == 0
    assert panel.age_days(date(2027, 2, 21)) == 32


@pytest.mark.parametrize("measured_on", ["unmeasured", "2027-1-20", "", "2027-02-30", "20270120"])
def test_a_measured_calibration_names_the_day_it_was_measured(measured_on):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        measured(measured_on=measured_on)


def test_a_calibration_holds_three_transfers():
    with pytest.raises(ValueError, match="three transfers"):
        measured(transfer=(LINEAR, LINEAR))


def test_a_record_reads_back_as_the_calibration_it_describes(tmp_path):
    panel = read_calibration(_write(tmp_path, _record()))

    assert (panel.id, panel.measured_on, panel.standard, panel.observer) == (
        "rig1@2027-01-20", "2027-01-20", False, "CIE 1931 2°")
    assert (panel.red, panel.background) == (xyY(0.68, 0.31, 45.0), xyY(0.3127, 0.329, 20.0))
    assert panel.transfer == (Transfer(levels=(0.0, 0.5, 1.0), fractions=(0.0, 0.2, 1.0)),) * 3
    assert panel.max_cone_contrast is None
    assert read_calibration(_write(tmp_path, _record(max_cone_contrast=0.2))).max_cone_contrast == 0.2


@pytest.mark.parametrize("change, said", [
    ({"id": "  "}, "id is empty"),
    ({"id": "x" * 65}, "at most 64 characters"),
    ({"extra": 1}, "extra"),
    ({"observer": 3}, "observer is text"),
    ({"measured_on": "last week"}, "YYYY-MM-DD"),
    ({"primaries": {"red": [0.6, 0.3, 40.0], "green": [0.3, 0.6, 100.0]}}, "red, green and blue"),
    ({"background": [0.3, 0.3]}, "three numbers"),
    ({"transfer": {c: [[0.0, 0.0], [1.0, 0.8]] for c in ("red", "green", "blue")}}, "end at 1"),
    ({"transfer": {c: [0.0, 1.0] for c in ("red", "green", "blue")}}, "pairs"),
    ({"max_cone_contrast": -1}, "positive"),
    # Too large for a float: `math.isfinite` raises `OverflowError` on it, not a ValueError.
    ({"background": [0.3127, 0.329, 10**400]}, "three numbers"),
])
def test_a_record_that_is_not_one_is_refused_naming_what_is_wrong(tmp_path, change, said):
    with pytest.raises(ValueError, match=said):
        read_calibration(_write(tmp_path, _record(**change)))


@pytest.mark.parametrize("field", ["id", "measured_on", "observer", "primaries", "background", "transfer"])
def test_a_record_missing_a_field_is_refused_naming_it(tmp_path, field):
    record = _record()
    del record[field]

    with pytest.raises(ValueError, match=f"has no {field}"):
        read_calibration(_write(tmp_path, record))


@pytest.mark.parametrize("text, said", [("{", "not JSON"), ("[1, 2]", "one JSON object")])
def test_a_file_that_is_no_record_is_refused(tmp_path, text, said):
    path = tmp_path / "cal.json"
    path.write_text(text)

    with pytest.raises(ValueError, match=said):
        read_calibration(path)
