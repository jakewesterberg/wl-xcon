"""The warnings list's sources and rules (engine spec §19.2): each entry says what is imperfect
and the session kinds it is acceptable in."""

from datetime import date, timedelta

import pytest

from _calibrations import measured
from wl_xcon import warnlist
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
from wl_xcon.link import PreflightItem
from wl_xcon.photometry import SRGB, Calibration
from wl_xcon.warnlist import Entry
from wl_xcon.welfare import Deployment

TODAY = date(2027, 1, 20)


def _measured(days_before: int) -> Calibration:
    """The shared measured test panel (`_calibrations.measured`), measured `days_before` days
    before `TODAY`."""
    return measured(measured_on=(TODAY - timedelta(days=days_before)).isoformat())


def test_the_default_calibration_is_one_entry_acceptable_in_every_kind():
    (entry,) = warnlist.of_calibration(SRGB, TODAY)

    assert (entry.code, entry.accepted_in) == ("default calibration", SESSION_KINDS)
    assert "sRGB standard" in entry.detail and "80 cd/m²" in entry.detail and "UNVERIFIED" in entry.detail


@pytest.mark.parametrize("days, listed", [(0, False), (30, False), (31, True), (400, True)])
def test_a_calibration_is_listed_past_thirty_days_and_never_refused(days, listed):
    found = warnlist.of_calibration(_measured(days), TODAY)

    assert bool(found) is listed
    if listed:
        (entry,) = found
        assert (entry.code, entry.accepted_in) == ("calibration age", SESSION_KINDS)
        assert f"{days} days ago" in entry.detail and "rig1" in entry.detail


def test_a_calibration_dated_after_today_is_accepted_in_no_kind():
    """The review's C1: no session kind accepts it, so every run's pre-flight fails on it --
    and nothing else does: an open, an end and a return never read it (Call 19)."""
    (entry,) = warnlist.of_calibration(_measured(-1), TODAY)

    assert (entry.code, entry.accepted_in) == ("calibration age", ())
    assert [warnlist.refused([entry], kind) for kind in SESSION_KINDS] == [[entry]] * 3
    assert "after today" in entry.detail and "every run's pre-flight fails" in entry.detail


def test_a_calibration_that_will_not_load_is_one_entry_no_kind_accepts():
    refusal = "refused: the calibration tests/_rig.py names, cal.json: it is not JSON (Expecting value)"

    (entry,) = warnlist.of_unloaded(refusal)

    assert (entry.code, entry.accepted_in) == ("calibration record", ())
    assert entry.detail.startswith(refusal) and "every run's pre-flight fails" in entry.detail


def test_a_chaired_session_lists_its_free_head_and_a_fixed_one_lists_nothing():
    (entry,) = warnlist.of_deployment(Deployment.RIG_CHAIRED)

    assert (entry.code, entry.accepted_in) == ("head free", SESSION_KINDS)
    assert warnlist.of_deployment(Deployment.RIG_FIXED) == []


def test_only_a_findings_warnings_join_the_list():
    findings = [Finding("unlit", "no light"),
                Finding("custom-component-needs-review", "review", blocking=False),
                Finding("color-on-default", "names colors", blocking=False, accepted_in=NOT_RECORDING)]

    assert warnlist.of_findings(findings) == [Entry("color-on-default", "names colors", NOT_RECORDING)]


def test_only_an_unknown_pre_flight_item_joins_the_list_under_its_own_name_and_sentence():
    items = [PreflightItem("pump calibration", "unknown", "no pump calibration"),
             PreflightItem("task checks", "pass", "passes"),
             PreflightItem("bounded config", "fail", "gone")]

    assert warnlist.of_unknowns(items) == [Entry("pump calibration", "no pump calibration", SESSION_KINDS)]


def test_refused_and_owed_answer_by_kind_and_by_what_was_accepted():
    a = Entry("a", "one", NOT_RECORDING)
    b = Entry("b", "two", SESSION_KINDS)

    assert warnlist.refused([a, b], "recording") == [a]
    assert warnlist.refused([a, b], "training") == []
    assert warnlist.owed([a, b], {("a", "one")}) == [b]
    assert warnlist.owed([a, b], {("a", "a different sentence")}) == [a, b]
    assert warnlist.sentence([a, b]) == "a: one; b: two"


def test_an_entry_names_only_the_three_kinds():
    with pytest.raises(ValueError, match="training, piloting or recording"):
        Entry("a", "one", ("demo",))
    with pytest.raises(ValueError, match="training, piloting or recording"):
        warnlist.refused([], "demo")
