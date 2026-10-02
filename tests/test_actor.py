"""`wl_xcon/actor.py`: who sent a command (b2b spec §6)."""

from __future__ import annotations

import pytest

from wl_xcon import actor
from wl_xcon import link
from wl_xcon.actor import Box, Member

MEMBER = Member(
    name="Jake Westerberg",
    account="user-1",
    issuer="https://wl.works/api/auth",
    token_id="jti-1",
)


def test_each_kind_prints_as_a_person_reads_it():
    assert str(Box("jake")) == "jake (box, unverified)"
    assert str(MEMBER) == "Jake Westerberg (wl.works)"
    assert str(Box("")) == ""


def test_a_box_name_dressed_as_a_member_still_prints_as_a_box():
    assert str(Box("Jake Westerberg (wl.works)")) == (
        "Jake Westerberg (wl.works) (box, unverified)"
    )


def test_to_map_and_from_map_round_trip_both_kinds():
    assert actor.to_map(Box("jake")) == {"kind": "box", "name": "jake"}
    assert actor.to_map(MEMBER) == {
        "kind": "member",
        "name": "Jake Westerberg",
        "account": "user-1",
        "issuer": "https://wl.works/api/auth",
        "token_id": "jti-1",
    }
    assert actor.from_map(actor.to_map(Box("jake"))) == Box("jake")
    assert actor.from_map(actor.to_map(MEMBER)) == MEMBER


@pytest.mark.parametrize("not_one", ["jake", None, 3, ("box", "jake")])
def test_to_map_refuses_anything_but_an_actor(not_one):
    with pytest.raises(TypeError):
        actor.to_map(not_one)


def test_to_map_or_none_passes_nobody_through():
    assert actor.to_map_or_none(None) is None
    assert actor.to_map_or_none(Box("jake")) == {"kind": "box", "name": "jake"}


@pytest.mark.parametrize(
    "data",
    [
        "jake",
        None,
        {"kind": "box"},
        {"kind": "box", "name": 3},
        {"kind": "box", "name": "jake", "extra": 1},
        {"kind": "member", "name": "J", "account": "a", "issuer": "i"},
        {"kind": "member", "name": "", "account": "a", "issuer": "i", "token_id": "t"},
        {"kind": "member", "name": "J", "account": "a", "issuer": "i", "token_id": 5},
        {"kind": "admin", "name": "jake"},
        {"kind": "box", "name": "x" * 201},
    ],
)
def test_from_map_refuses_what_is_not_an_actor(data):
    with pytest.raises(actor.NotAnActor):
        actor.from_map(data)


def test_from_map_keeps_an_empty_box_name_for_a_record_that_has_one():
    """A terminal confirmation given without --as is recorded with an empty name;
    reading it back must work. The wire refuses an empty name separately."""
    assert actor.from_map({"kind": "box", "name": ""}) == Box("")


def test_read_takes_a_map_a_legacy_string_and_null():
    """Review Focus 1: a record written before b2b holds a string `by`."""
    assert actor.read({"kind": "box", "name": "jake"}) == Box("jake")
    assert actor.read("jake (box, unverified)") == "jake (box, unverified)"
    assert actor.read(None) is None


def test_shown_takes_an_actor_a_legacy_string_and_nobody():
    assert actor.shown(MEMBER) == "Jake Westerberg (wl.works)"
    assert actor.shown("jake (box, unverified)") == "jake (box, unverified)"
    assert actor.shown(None) == ""


def test_the_limit_is_the_wires():
    assert actor.TEXT_LIMIT == link.TEXT_LIMIT
