"""The warnings list's sources and rules (engine spec §19.2): each entry says what is imperfect
and the session kinds it is acceptable in."""

import re
from datetime import date, timedelta

import pytest

from _calibrations import measured
from wl_xcon import warnlist
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
from wl_xcon.link import NOTE_LIMIT, PreflightItem
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


def test_a_calibration_dated_after_today_is_a_warning_in_every_kind_to_check_the_clock():
    """XC-352's E2 (the PI, 2026-10-11): its date or this host's clock is wrong, which a warning
    says, in every session kind, never a refusal (until then no kind accepted it)."""
    (entry,) = warnlist.of_calibration(_measured(-1), TODAY)

    assert (entry.code, entry.accepted_in) == ("calibration age", SESSION_KINDS)
    assert [warnlist.refused([entry], kind) for kind in SESSION_KINDS] == [[]] * 3
    assert "after today" in entry.detail and "check this host's clock" in entry.detail


def test_a_calibration_that_will_not_load_is_a_warning_that_the_default_runs_in_its_place():
    """XC-352's E1 (the PI, 2026-10-11): the session falls back to the sRGB default with a
    warning, in every kind, quoting why the record would not load -- cut, so the whole sentence
    stays within what an open's form sends back (`link.NOTE_LIMIT`)."""
    refusal = "refused: the calibration tests/_rig.py names, cal.json: it is not JSON (Expecting value)"

    (entry,) = warnlist.of_unloaded(refusal)
    (long,) = warnlist.of_unloaded("refused: " + "x" * 2_000)

    assert (entry.code, entry.accepted_in) == ("calibration record", SESSION_KINDS)
    assert entry.detail.startswith(refusal)
    assert "this session runs on the default calibration, the sRGB standard" in entry.detail
    assert len(long.detail) <= NOTE_LIMIT and "…" in long.detail
    # Cut in its middle: a record's refusal names its path first and why it would not load last.
    assert long.detail.startswith("refused: xxx")
    # The default's own warning says why it stands in, never that the rig names none (the
    # warnings-over-refusals review's M4).
    (default,) = warnlist.of_calibration(SRGB, TODAY, unloaded=True)
    assert default.detail.startswith("the calibration record the rig names would not load, so ")


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
    with pytest.raises(TypeError, match="a tuple of session kinds, not list"):
        Entry("a", "one", list(SESSION_KINDS))
    with pytest.raises(ValueError, match="names 'training' twice"):
        Entry("a", "one", ("training", "piloting", "training"))


@pytest.mark.parametrize("code", ["", "   "])
def test_an_entry_refuses_an_empty_code(code):
    with pytest.raises(ValueError, match="this one is empty"):
        Entry(code, "one", SESSION_KINDS)


@pytest.mark.parametrize("held", [",", "(", ")", "×"])
def test_an_entry_refuses_a_code_holding_what_the_preflight_lists_codes_with(held):
    """The engine B final review: a run's pre-flight names the codes it asks to accept as a
    list in parentheses, a repeated one with its count ("luminance-step ×30"), and its rule
    that a cut never drops a name relies on no code holding one of these."""
    with pytest.raises(ValueError, match=f"never holds {re.escape(repr(held))}"):
        Entry(f"luminance{held}step", "one", SESSION_KINDS)
    with pytest.raises(ValueError, match="training, piloting or recording"):
        warnlist.refused([], "demo")
