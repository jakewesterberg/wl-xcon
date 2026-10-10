"""The display's color calibration as a record (engine spec §7, §12.6): the default is the sRGB
standard and says so; a measured one carries its id, its date and a measured transfer per
channel."""

import json
import os
from datetime import date
from pathlib import Path

import pytest

from _calibrations import BACKGROUND, LINEAR, OBSERVER, PRIMARIES, measured, promptly
from _rig import PATH as RIG_FILE
from _rig import RIG, naming
from wl_xcon.cli import _load_calibration, _load_rig
from wl_xcon.photometry import (
    D65,
    DKL,
    SRGB,
    SRGB_TRANSFER,
    SRGB_WHITE_CD_M2,
    RECORD_LIMIT,
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
    # Solved independently, in exact rational arithmetic (2026-10-08).
    assert (SRGB.red.Y, SRGB.green.Y, SRGB.blue.Y) == pytest.approx(
        (17.011120469720822, 57.213494301420475, 5.775385228858696), rel=1e-12)
    assert SRGB.spectra is None


def test_full_drive_on_the_default_is_the_standards_white_and_no_brighter():
    assert SRGB_WHITE_CD_M2 == 80.0
    assert SRGB.weights(xyY(*D65, SRGB_WHITE_CD_M2)) == pytest.approx((1.0, 1.0, 1.0), abs=1e-12)
    assert unrealizable(xyY(*D65, SRGB_WHITE_CD_M2), SRGB) is None
    assert unrealizable(xyY(*D65, SRGB_WHITE_CD_M2 + 0.01), SRGB) is not None


def test_a_cone_color_converts_on_the_default_and_on_a_measured_calibration_with_spectra():
    """Engine build A2: no stored cone-contrast limit; the full conversion decides (spec §7.4)."""
    gray = xyY(*D65, 20.0)

    assert unrealizable(DKL(l_m=0.08), SRGB, gray) is None
    assert unrealizable(DKL(l_m=0.08), measured(), gray) is None
    assert "outside [0, 1]" in unrealizable(DKL(l_m=-0.3), SRGB, gray)
    assert "no background was given" in unrealizable(DKL(l_m=0.08), SRGB)
    assert "measured without spectra" in unrealizable(DKL(l_m=0.08), measured(spectra=None), gray)


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


@pytest.mark.parametrize("over, said", [
    ({"red": xyY(0.68, 0.0, 45.0)}, "red primary"),
    ({"green": xyY(-0.01, 0.69, 140.0)}, "green primary"),
    ({"blue": xyY(0.6, 0.5, 12.0)}, "blue primary"),
    ({"red": xyY(0.68, 0.31, 0.0)}, "red primary"),
    ({"green": xyY(0.26, float("nan"), 140.0)}, "green primary"),
    ({"background": xyY(0.3127, 0.0, 20.0)}, "background"),
    ({"background": xyY(0.3127, 0.329, -1.0)}, "background"),
    # On the line from the red primary to the blue one.
    ({"green": xyY(0.41, 0.18, 140.0)}, "do not span a gamut"),
])
def test_a_calibration_whose_lights_no_display_makes_is_refused_naming_which(over, said):
    with pytest.raises(ValueError, match=said):
        measured(**over)


def test_a_black_background_is_a_light_a_display_makes():
    assert measured(background=xyY(0.3127, 0.329, 0.0)).background.Y == 0.0


def test_a_color_whose_chromaticity_y_is_not_positive_is_refused_by_name():
    assert "chromaticity y must be positive" in unrealizable(xyY(0.3, 0.0, 10.0), SRGB)


def test_a_record_reads_back_as_the_calibration_it_describes(tmp_path):
    panel = read_calibration(_write(tmp_path, _record()))

    assert (panel.id, panel.measured_on, panel.standard, panel.observer) == (
        "rig1@2027-01-20", "2027-01-20", False, "CIE 1931 2°")
    assert (panel.red, panel.background) == (xyY(0.68, 0.31, 45.0), xyY(0.3127, 0.329, 20.0))
    assert panel.transfer == (Transfer(levels=(0.0, 0.5, 1.0), fractions=(0.0, 0.2, 1.0)),) * 3
    assert read_calibration(_write(tmp_path, _record(id="rig 1 (left)"))).id == "rig 1 (left)"


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
    # Engine build A2 converts cone colors in full and keeps no stored limit (spec §7.4).
    ({"max_cone_contrast": 0.2}, "max_cone_contrast, which a calibration record does not"),
    ({"observer": " "}, "names the observer"),
    # Too large for a float: `math.isfinite` raises `OverflowError` on it, not a ValueError.
    ({"background": [0.3127, 0.329, 10**400]}, "three numbers"),
    ({"primaries": {**PRIMARIES, "red": [0.68, 0.0, 45.0]}}, "red primary"),
    ({"id": " rig1"}, "begins or ends with whitespace"),
    ({"id": "rig1\n"}, "begins or ends with whitespace"),
    ({"id": "rig\x1b[2Jone"}, "does not print"),
    ({"id": "rig\u202eone"}, "does not print"),
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


@pytest.mark.parametrize("text, said", [
    ("{", "not JSON"),
    ("[1, 2]", "one JSON object"),
    pytest.param("[" * 100_000 + "]" * 100_000, "not JSON", id="nested-100000-deep"),
    ('{"id": "a", "id": "b"}', "'id' twice"),
    ('{"primaries": {"red": [0.6, 0.3, 40.0], "red": [0.6, 0.3, 40.0]}}', "'red' twice"),
])
def test_a_file_that_is_no_record_is_refused(tmp_path, text, said):
    path = tmp_path / "cal.json"
    path.write_text(text)

    with pytest.raises(ValueError, match=said):
        read_calibration(path)


def test_a_record_larger_than_a_mebibyte_is_refused(tmp_path):
    with pytest.raises(ValueError, match="larger than 1048576 bytes"):
        read_calibration(_write(tmp_path, _record(observer="x" * RECORD_LIMIT)))


def test_a_record_of_exactly_a_mebibyte_loads_and_one_byte_more_is_refused(tmp_path):
    """The bound is the largest file read, so a record at it loads (trailing whitespace is
    JSON's own) and one byte past it does not."""
    text = json.dumps(_record())
    path = tmp_path / "cal.json"
    path.write_text(text + " " * (RECORD_LIMIT - len(text)))
    assert path.stat().st_size == RECORD_LIMIT

    assert read_calibration(path).id == "rig1@2027-01-20"
    path.write_text(text + " " * (RECORD_LIMIT + 1 - len(text)))
    with pytest.raises(ValueError, match="larger than 1048576 bytes"):
        read_calibration(path)


def test_a_named_pipe_is_refused_without_waiting_for_a_writer(tmp_path):
    """The engine B final review: opening a named pipe to read waits until something writes
    to it, which held `wlx taskd` at its start. Refused as what it is, before a byte is read,
    and at once: nothing ever writes to this one."""
    pipe = tmp_path / "cal.json"
    os.mkfifo(pipe)

    with pytest.raises(ValueError, match=r"^it is a named pipe, not a regular file, so it was not read"):
        promptly(lambda: read_calibration(pipe), pipe)


def test_a_directory_is_refused_as_one(tmp_path):
    (tmp_path / "cal.json").mkdir()

    with pytest.raises(ValueError, match=r"^it is a directory, not a regular file, so it was not read"):
        read_calibration(tmp_path / "cal.json")


def test_a_rig_that_names_no_calibration_runs_on_the_default():
    assert RIG.calibration is None
    assert _load_calibration(RIG, RIG_FILE) is SRGB


def test_the_lab_rig_names_none_until_one_is_measured():
    assert _load_rig(Path("tasks/rig.py")).calibration is None


def test_a_rig_names_its_record_relative_to_its_own_folder(tmp_path):
    path = naming(tmp_path / "rig", "cal/rig1.json")
    (tmp_path / "rig" / "cal").mkdir()
    _write(tmp_path / "rig" / "cal", _record(), "rig1.json")

    assert _load_calibration(_load_rig(path), path).id == "rig1@2027-01-20"


@pytest.mark.parametrize("content, said", [
    (None, "No such file"),
    ("{", "not JSON"),
    (json.dumps(_record(extra=1)), "extra"),
    (json.dumps(_record(transfer={c: [[0.0, 0.5], [0.5, 0.4], [1.0, 1.0]] for c in ("red", "green", "blue")})), "never fall"),
])
def test_a_named_record_that_will_not_load_refuses_and_never_falls_back(tmp_path, content, said):
    path = naming(tmp_path, "cal.json")
    if content is not None:
        (tmp_path / "cal.json").write_text(content)

    with pytest.raises(SystemExit) as refused:
        _load_calibration(_load_rig(path), path)

    assert str(refused.value).startswith("refused: the calibration") and said in str(refused.value)


@pytest.mark.parametrize("calibration", [3, "", "  "])
def test_a_calibration_that_is_not_a_path_is_refused(tmp_path, calibration):
    path = naming(tmp_path, calibration)

    with pytest.raises(SystemExit, match="the path of a calibration record"):
        _load_calibration(_load_rig(path), path)
