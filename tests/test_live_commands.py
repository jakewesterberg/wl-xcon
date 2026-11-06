"""The wire's three commands of engine build C3 (the C3 spec §6 and §8; the C3 plan, Call 20).

A setting handed back (`link.HandBack`, `hand_back`; the PI, 2026-10-30, Q7a), a drawn range
changed live (`link.SetRange`, `range`; Q7b) and a revert to an earlier moment (`link.Revert`,
`revert`; TSK-43), each its own command: encoded and decoded by the wire's own rules, and built
from the page's bodies (`serve._SHAPES`) by the same function (`link._command_from`), so the page
hears the rig's own sentence before anything is queued. **A range is never a `SetParameter`**: its
numbers are decoded by `link._setting`, M8's rule, welfare-listed and called unchanged, and a word
among them is refused. What a session does with each is `taskd`'s, tested where it acts on them.
"""

from __future__ import annotations

import time

import pytest

from wl_xcon import link
from wl_xcon.actor import Box
from wl_xcon.serve import BadCommand, parse_command

#: "jake" typed at the box, as a hand-built packet carries it: an actor's map (b2b spec §6).
JAKE = {"kind": "box", "name": "jake"}
#: Nine numbers, one more than a range may carry (`link.NUMBERS_LIMIT`).
_NINE = {f"n{i}": float(i) for i in range(9)}


def _packed(**fields) -> bytes:
    import msgpack

    return msgpack.packb(fields, use_bin_type=True)


def _sent() -> list:
    """One of each as a console sends it: a hand-back, a range of each kind of draw a person may
    change live (the C3 spec §6), and a revert to the run's start and to the largest change id
    the wire carries. Built when called, never at import, so each test of a `link` without the
    three fails on the name rather than the file failing to collect."""
    jake = Box("jake")
    return [
        link.HandBack(name="fix_hold", by=jake),
        link.SetRange(name="target_size", numbers={"low": 0.5, "high": 2.0}, by=jake),
        link.SetRange(name="contrast", numbers={"mean": 0.5, "sd": 0.1, "low": 0.2, "high": 0.8},
                      by=jake),
        link.SetRange(name="foreperiod", numbers={"minimum": 0.75, "mean": 1.0, "maximum": 1.25},
                      by=jake),
        link.Revert(change=0, by=jake),
        link.Revert(change=link.TRIALS_LIMIT, by=jake),
    ]


def _drained(rig, *, tries=50, pause=0.01) -> list:
    """`rig.drain()` until it returns a command, or `[]` after `tries * pause` seconds: ZeroMQ's
    I/O thread may not yet have moved a command sent in the statement before, and nothing is
    lost (`tests/test_link.py`'s `_drain_until` says why)."""
    for _ in range(tries):
        got = rig.drain()
        if got:
            return got
        time.sleep(pause)
    return []


def test_a_hand_back_a_range_and_a_revert_round_trip_the_wire(zmq_cleanup):
    """Each survives `_encode_command` and `_decode_command` whole, with who sent it, and crosses a
    real socket from a console to the rig in the order sent, refused nowhere, as the C2a and C2b
    controls do (`tests/test_link.py`)."""
    sent = _sent()

    restored = [link._decode_command(link._encode_command(command)) for command in sent]

    assert restored == sent
    assert [type(command) for command in restored] == [type(command) for command in sent]
    assert (link.HandBack.KIND, link.SetRange.KIND, link.Revert.KIND) == (
        "hand_back", "range", "revert")
    rig = zmq_cleanup(link.ZmqLink(pub_endpoint="tcp://127.0.0.1:0",
                                   rep_endpoint="tcp://127.0.0.1:0"))
    console = zmq_cleanup(link.ZmqConsole(rig.pub_endpoint, rig.rep_endpoint))
    seen = []
    for command in sent:
        console.send(command)
        seen += _drained(rig)
    assert seen == sent and rig.refused == []


def test_a_page_body_for_each_is_built_by_the_wires_own_rules():
    """The page sends each by the wire's field names (`serve._SHAPES`), and `parse_command` builds
    it with `link._command_from`, as it builds `clear`, `drum` and `training` (engine build C2a): a
    range's whole numbers arrive as floats, the page hears the rig's own sentence word for word,
    and a field a kind does not take is refused, not ignored."""
    jake = Box("jake")
    expected = [
        link.HandBack(name="fix_hold", by=jake),
        link.SetRange(name="foreperiod",
                      numbers={"minimum": 750.0, "mean": 1000.0, "maximum": 1250.0}, by=jake),
        link.Revert(change=3, by=jake),
    ]
    bodies = [
        {"kind": "hand_back", "by": "jake", "name": "fix_hold"},
        {"kind": "range", "by": "jake", "name": "foreperiod",
         "numbers": {"minimum": 750, "mean": 1000, "maximum": 1250}},
        {"kind": "revert", "by": "jake", "change": 3},
    ]

    built = [parse_command(body) for body in bodies]

    assert built == expected
    assert [type(number) for number in built[1].numbers.values()] == [float, float, float]
    for body in ({"kind": "hand_back", "by": "jake", "name": ""},
                 {"kind": "range", "by": "jake", "name": "foreperiod", "numbers": {}},
                 {"kind": "revert", "by": "jake", "change": -1}):
        with pytest.raises(link.CommandRefused) as wire:
            link._command_from({**body, "by": JAKE})
        with pytest.raises(BadCommand) as page:
            parse_command(body)
        assert str(page.value) == wire.value.why
    for body, field in (
        ({"kind": "hand_back", "by": "jake", "name": "fix_hold", "value": 1.0}, "value"),
        ({"kind": "range", "by": "jake", "name": "foreperiod", "numbers": {"mean": 1.0},
          "value": 1.0}, "value"),
        ({"kind": "revert", "by": "jake", "change": 3, "name": "fix_hold"}, "name"),
    ):
        with pytest.raises(BadCommand, match=f"^a {body['kind']} command takes no {field}$"):
            parse_command(body)


@pytest.mark.parametrize(
    ("fields", "name", "said"),
    [
        ({"kind": "hand_back", "by": JAKE}, "hand_back", "name is text of 1 to 200 characters"),
        ({"kind": "hand_back", "name": "", "by": JAKE}, "hand_back",
         "name is text of 1 to 200 characters"),
        ({"kind": "hand_back", "name": "x" * 201, "by": JAKE}, "hand_back",
         "name is text of 1 to 200 characters"),
        ({"kind": "hand_back", "name": "fix_hold"}, "hand_back", "must say who sent it"),
        ({"kind": "range", "numbers": {"low": 1.0}, "by": JAKE}, "range",
         "name is text of 1 to 200 characters"),
        ({"kind": "range", "name": "foreperiod", "by": JAKE}, "range",
         "numbers are 1 to 8 named numbers"),
        ({"kind": "range", "name": "foreperiod", "numbers": {}, "by": JAKE}, "range",
         "numbers are 1 to 8 named numbers"),
        ({"kind": "range", "name": "foreperiod", "numbers": [0.5, 2.0], "by": JAKE}, "range",
         "numbers are 1 to 8 named numbers"),
        ({"kind": "range", "name": "foreperiod", "numbers": _NINE, "by": JAKE}, "range",
         "numbers are 1 to 8 named numbers"),
        ({"kind": "range", "name": "foreperiod", "numbers": {"": 1.0}, "by": JAKE}, "range",
         "is named by text of 1 to 200 characters"),
        ({"kind": "range", "name": "foreperiod", "numbers": {"x" * 201: 1.0}, "by": JAKE},
         "range", "is named by text of 1 to 200 characters"),
        ({"kind": "range", "name": "foreperiod", "numbers": {"low": None}, "by": JAKE},
         "foreperiod", "a setting is a finite number"),
        ({"kind": "range", "name": "foreperiod", "numbers": {"low": float("inf")}, "by": JAKE},
         "foreperiod", "which is not a real number"),
        ({"kind": "range", "name": "foreperiod", "numbers": {"low": 1.0}}, "range",
         "must say who sent it"),
        ({"kind": "revert", "by": JAKE}, "revert",
         "change is a whole number from 0 to 9223372036854775807"),
        ({"kind": "revert", "change": -1, "by": JAKE}, "revert",
         "change is a whole number from 0 to 9223372036854775807"),
        ({"kind": "revert", "change": 2**63, "by": JAKE}, "revert",
         "change is a whole number from 0 to 9223372036854775807"),
        ({"kind": "revert", "change": 2.0, "by": JAKE}, "revert",
         "change is a whole number from 0 to 9223372036854775807"),
        ({"kind": "revert", "change": True, "by": JAKE}, "revert",
         "change is a whole number from 0 to 9223372036854775807"),
        ({"kind": "revert", "change": "3", "by": JAKE}, "revert",
         "change is a whole number from 0 to 9223372036854775807"),
        ({"kind": "revert", "change": 3}, "revert", "must say who sent it"),
    ],
    ids=[
        "hand back, no name", "hand back, empty name", "hand back, long name",
        "hand back, from nobody", "range, no name", "range, no numbers", "range, none",
        "range, a list", "range, nine", "range, a number named by nothing",
        "range, a long number name", "range, a number that is none", "range, infinity",
        "range, from nobody", "revert, no change", "revert, below 0", "revert, past the wire",
        "revert, a float", "revert, a bool", "revert, text", "revert, from nobody",
    ],
)
def test_a_malformed_hand_back_range_or_revert_is_refused_with_its_sentence(fields, name, said):
    """M8's rule for every field (P4d-2b b2a): a command that decoded and is malformed is refused
    where it is decoded, with a sentence, filed under its kind -- or, for a number, under the
    setting it was for, as `_setting` files a value -- and the session runs on (`ZmqLink.drain`
    makes it a row on every console's feed)."""
    assert fields["kind"] in (link.HandBack.KIND, link.SetRange.KIND, link.Revert.KIND)

    with pytest.raises(link.CommandRefused) as refused:
        link._decode_command(_packed(**fields))

    assert refused.value.name == name
    assert said in refused.value.why and "so it is refused" in refused.value.why


def test_a_ranges_numbers_pass_through_setting_unchanged_and_a_word_is_refused(monkeypatch):
    """The C3 spec §6: "its numbers decoded by `link._setting` unchanged". M8's rule,
    welfare-listed, is called once for each number with the setting's name, so a number is what a
    setting's value may be -- a whole number made a float; `True`, `nan`, an integer too large for
    a float and an over-long word refused by `_setting`'s own sentences, filed under the setting
    -- and a word, which `_setting` lets through for a categorical setting, is refused, on the
    wire and from the page alike, since a range's numbers are numbers."""
    expected = link.SetRange(name="foreperiod", numbers={"minimum": 750.0, "maximum": 1250.0},
                             by=Box("jake"))
    calls = []
    setting = link._setting

    def spy(value, name, by):
        calls.append((value, name, by))
        return setting(value, name, by)

    monkeypatch.setattr(link, "_setting", spy)
    built = link._command_from({"kind": "range", "name": "foreperiod",
                                "numbers": {"minimum": 750, "maximum": 1250}, "by": JAKE})
    monkeypatch.undo()

    assert built == expected
    assert calls == [(750, "foreperiod", Box("jake")), (1250, "foreperiod", Box("jake"))]
    for value in (True, float("nan"), 10**400, "w" * 201):
        with pytest.raises(link.CommandRefused) as wire:
            link._command_from({"kind": "range", "name": "foreperiod",
                                "numbers": {"minimum": value}, "by": JAKE})
        with pytest.raises(link.CommandRefused) as alone:
            link._setting(value, "foreperiod", Box("jake"))
        assert (wire.value.name, wire.value.why) == ("foreperiod", alone.value.why)
    with pytest.raises(link.CommandRefused) as word:
        link._command_from({"kind": "range", "name": "foreperiod",
                            "numbers": {"minimum": "wide"}, "by": JAKE})
    assert word.value.name == "foreperiod"
    assert word.value.why == (
        "'foreperiod' was sent the word 'wide' as its 'minimum': a drawn range's numbers are "
        "finite numbers, never a word, so it is refused and the session runs on")
    with pytest.raises(BadCommand) as page:
        parse_command({"kind": "range", "by": "jake", "name": "foreperiod",
                       "numbers": {"minimum": "wide"}})
    assert str(page.value) == word.value.why
