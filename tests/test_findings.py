"""What a finding says about a session's kind (engine spec §19.2): a refusal refuses in every
kind; a warning states the kinds it is acceptable in and refuses outside them; a review note
refuses nowhere."""

import pytest

from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding, kind_named


def test_the_three_kinds_are_the_pis_words():
    assert SESSION_KINDS == ("training", "piloting", "recording")
    assert NOT_RECORDING == ("training", "piloting")


def test_a_refusal_refuses_in_every_kind_and_with_none_named():
    refusal = Finding("unlit", "no light")

    assert [refusal.refuses(kind) for kind in (*SESSION_KINDS, None)] == [True] * 4
    assert not refusal.is_warning


def test_a_warning_refuses_only_outside_the_kinds_it_names():
    warning = Finding("color-on-default", "names colors", blocking=False, accepted_in=NOT_RECORDING)

    assert warning.is_warning
    assert [warning.refuses(kind) for kind in SESSION_KINDS] == [False, False, True]
    assert warning.refuses(None) is False


def test_a_review_note_refuses_nowhere_and_is_no_warning():
    note = Finding("custom-component-needs-review", "needs review", blocking=False)

    assert not note.is_warning
    assert not any(note.refuses(kind) for kind in (*SESSION_KINDS, None))


@pytest.mark.parametrize("fields, said", [
    (dict(blocking=False, accepted_in=("demo",)), "training, piloting or recording"),
    (dict(blocking=False, accepted_in=("training", "training")), "twice"),
    (dict(blocking=False, accepted_in=["training"]), "tuple"),
    (dict(blocking=True, accepted_in=("training",)), "refuses in every kind"),
])
def test_a_finding_names_only_the_three_kinds_once_each(fields, said):
    with pytest.raises((ValueError, TypeError), match=said):
        Finding("x", "y", **fields)


@pytest.mark.parametrize("kind", ["Training", "", 3, None])
def test_a_kind_that_is_not_one_of_the_three_is_named_as_such(kind):
    with pytest.raises(ValueError, match="training, piloting or recording"):
        kind_named(kind)


def test_refuses_names_an_unknown_kind_rather_than_answering():
    with pytest.raises(ValueError, match="training, piloting or recording"):
        Finding("x", "y").refuses("demo")
