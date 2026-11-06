"""The gaze ingest, against replayed OpenIrisDPI payloads.

Schema verified 2026-09-01 from the client that ships in the OpenIrisDPI repo
(`PythonUDP/openiris_udp_client.py`): send `WAITFORDATA` to UDP 9003, receive JSON
with `Left`/`Right`, each carrying `FrameNumber`, `Pupil.Center.{X,Y}`,
`Pupil.Size.{Width,Height}` and a `CRs` list, of which index 0 is P1 and index 3 is
P4.

Replayed rather than synthetic: S11 §2 asks for it, and a synthetic trace exercises
the parser against exactly the assumptions that wrote it.
"""

import json
import math

import pytest

from wl_xcon.eye import Replay, Sample, Tracker, parse

PAYLOAD = json.dumps(
    {
        "Left": {
            "FrameNumber": 1200,
            "Pupil": {"Center": {"X": 320.5, "Y": 240.25}, "Size": {"Width": 30.0, "Height": 28.0}},
            "CRs": [
                {"X": 300.0, "Y": 230.0},
                {"X": 0.0, "Y": 0.0},
                {"X": 0.0, "Y": 0.0},
                {"X": 296.0, "Y": 227.0},
            ],
        },
        "Right": {
            "FrameNumber": 1200,
            "Pupil": {"Center": {"X": 640.0, "Y": 241.0}, "Size": {"Width": 31.0, "Height": 29.0}},
            "CRs": [
                {"X": 620.0, "Y": 232.0},
                {"X": 0.0, "Y": 0.0},
                {"X": 0.0, "Y": 0.0},
                {"X": 615.0, "Y": 228.0},
            ],
        },
    }
)


def test_a_payload_parses_into_both_eyes():
    sample = parse(PAYLOAD, at=10.0)

    assert sample.at == 10.0
    assert sample.left.frame == 1200
    assert sample.left.pupil == (320.5, 240.25)
    assert sample.right.pupil == (640.0, 241.0)


def test_the_gaze_signal_is_the_difference_between_the_two_purkinje_images():
    """P1 minus P4 is the whole reason this tracker exists.

    Both images move with the eye *and* with the camera relative to the head, so
    either alone confounds rotation with translation. Their difference cancels
    translation to first order, which is what buys DPI its arcminute precision --
    and taking the pupil centre instead would silently throw that away while still
    producing plausible numbers.
    """
    sample = parse(PAYLOAD, at=0.0)

    assert sample.left.dpi() == pytest.approx((4.0, 3.0))
    assert sample.right.dpi() == pytest.approx((5.0, 4.0))


def test_pupil_area_comes_from_the_ellipse_axes():
    sample = parse(PAYLOAD, at=0.0)

    assert sample.left.pupil_area == pytest.approx(30.0 * 28.0)


def test_a_malformed_payload_does_not_reach_the_trial_loop():
    """A dropped or truncated datagram is a stale frame, not a crash.

    UDP loses and truncates packets by design, and a parse error propagating into
    the frame loop would end a session for something the protocol does routinely.
    """
    assert parse("{not json", at=1.0) is None
    assert parse(json.dumps({"Left": {}}), at=1.0) is None


#: One eye of a datagram, its first and fourth Purkinje images to be filled in, and its frame.
_EYE = ('{"FrameNumber": %s, "Pupil": {"Center": {"X": 1.0, "Y": 2.0}, '
        '"Size": {"Width": 3.0, "Height": 4.0}}, "CRs": [{"X": %s, "Y": %s}, {"X": 0, "Y": 0}, '
        '{"X": 0, "Y": 0}, {"X": %s, "Y": %s}]}')


def _datagram_reading(frame: str = "7", p1x: str = "10.0", p1y: str = "20.0", p4x: str = "30.0",
                      p4y: str = "40.0") -> str:
    """A datagram whose left eye reads the given JSON tokens, its right eye an ordinary one."""
    return '{"Left": %s, "Right": %s}' % (_EYE % (frame, p1x, p1y, p4x, p4y),
                                          _EYE % ("7", "10.0", "20.0", "30.0", "40.0"))


def _dropped(payload: str) -> None:
    """`payload` is no sample, and a tracker given it counts it dropped and holds nothing."""
    tracker = Tracker()
    tracker.accept(parse(payload, at=1.0))

    assert parse(payload, at=1.0) is None
    assert (tracker.received, tracker.dropped, tracker.latest) == (0, 1, None)


@pytest.mark.parametrize("token", ["Infinity", "-Infinity", "NaN"])
@pytest.mark.parametrize("where", ["p1x", "p1y", "p4x", "p4y"],
                         ids=["P1 across", "P1 up", "P4 across", "P4 up"])
def test_a_datagram_whose_gaze_is_no_finite_number_is_no_sample(token, where):
    """**A gaze value that is not finite is a lost sample** (the controller's ruling of
    2026-11-06): a datagram whose Purkinje image reads a bare `Infinity`, `-Infinity` or `NaN`,
    which Python's `json.loads` accepts, in any of its four coordinates, is no sample, as a
    malformed one is, so nothing after it does arithmetic on it and the tracker counts it dropped.
    The pupil, which no gaze reads, is not judged."""
    payload = _datagram_reading(**{where: token})
    assert json.loads(payload), "Python reads the bare token"

    _dropped(payload)


def test_a_datagram_whose_gaze_difference_overflows_is_no_sample():
    """**Nor one whose P1 - P4 is not finite** (the review of 498460d and d932cb3, its I3): images
    at 1e308 and -1e308 are numbers, but their difference, the gaze signal, overflows, which parse
    can tell from the floats it has just read."""
    _dropped(_datagram_reading(p1x="1e308", p4x="-1e308"))


@pytest.mark.parametrize("payload", [
    _datagram_reading(frame="Infinity"),
    _datagram_reading(frame="-Infinity"),
    _datagram_reading(frame="1e400"),
    _datagram_reading(p1x="9" * 309),
    _datagram_reading(p1x="1" * 5000),
    "[" * 65000 + "]" * 65000,
], ids=["frame Infinity", "frame -Infinity", "frame 1e400", "a 309-digit integer",
        "a 5000-digit integer", "65000 nested brackets"])
def test_parse_never_raises(payload):
    """**Any failure to read a datagram makes it no sample** (the controller's ruling of
    2026-11-06, on the review's I1: nothing from the tracker may raise mid-trial): a frame number
    that is no integer (`int` of an infinity raises `OverflowError`), an integer too large for a
    float (`OverflowError`), one of more digits than Python reads (`ValueError` inside
    `json.loads`), nesting too deep to read (`RecursionError`). Each raised, and `UdpSource.poll`
    and `Tracked.display` call `parse` every frame, so the session ended mid-trial."""
    _dropped(payload)


def test_a_sample_arriving_is_fresh_and_then_goes_stale():
    """Hold-last with a ceiling, which is P6's mitigation made concrete.

    ~2% of OpenIrisDPI frames take >= 10 ms and the worst measured is ~50 ms, so a
    tracker that reported loss on the first late frame would report loss constantly.
    One that never reported it would hand the trial loop a position the eye left
    long ago.
    """
    tracker = Tracker(staleness=0.05)
    tracker.accept(parse(PAYLOAD, at=1.000))

    assert tracker.state(at=1.010) == "ok"
    assert tracker.state(at=1.049) == "ok"
    assert tracker.state(at=1.060) == "lost"


def test_a_tracker_that_has_never_had_a_sample_is_lost_not_centred():
    """The dangerous default. A tracker reporting (0, 0) before its first sample
    puts gaze exactly on a fixation point that nobody is looking at."""
    tracker = Tracker(staleness=0.05)

    assert tracker.state(at=0.0) == "lost"
    assert tracker.latest is None


def test_the_last_good_sample_is_held_through_a_stall():
    tracker = Tracker(staleness=0.05)
    tracker.accept(parse(PAYLOAD, at=1.000))
    tracker.accept(None)

    assert tracker.latest.at == 1.000
    assert tracker.state(at=1.010) == "ok"


def test_replay_hands_back_recorded_payloads_in_order():
    """A replay source is a peer of the real one, so the parser is tested against
    what the tracker actually emitted rather than what we assumed it emits."""
    source = Replay([(0.000, PAYLOAD), (0.002, PAYLOAD)])

    first = source.poll(at=5.0)
    second = source.poll(at=5.002)

    assert isinstance(first, Sample) and isinstance(second, Sample)
    assert source.poll(at=5.004) is None


def test_the_tracker_counts_what_it_lost():
    """A stall census is a rig measurement (V3), and it starts here."""
    tracker = Tracker(staleness=0.05)
    tracker.accept(parse(PAYLOAD, at=1.0))
    tracker.accept(None)
    tracker.accept(None)
    tracker.accept(parse(PAYLOAD, at=1.1))

    assert tracker.received == 2
    assert tracker.dropped == 2


def test_the_client_speaks_the_protocol_over_a_real_socket():
    """A loopback server standing in for OpenIris.

    This is the part of the day-one path that can be built and proven *now*: the
    protocol is exercised over a real datagram socket, so what is left for January is
    a cable and an IP address rather than an integration.

    The server asserts the request string, because sending the wrong one is a failure
    that looks exactly like a tracker that is not running -- and on a rig, with an
    animal in the chair, that is the most expensive hour to spend debugging.
    """
    import socketserver
    import threading

    seen: list[bytes] = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            data, sock = self.request
            seen.append(data)
            sock.sendto(PAYLOAD.encode("utf-8"), self.client_address)

    server = socketserver.UDPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from wl_xcon.eye import REQUEST, UdpSource

        source = UdpSource(host="127.0.0.1", port=server.server_address[1], timeout=1.0)
        source.open()
        try:
            sample = source.poll(at=42.0)
        finally:
            source.close()
    finally:
        server.shutdown()
        server.server_close()

    assert seen == [REQUEST]
    assert sample is not None
    assert sample.at == 42.0
    assert sample.left.dpi() == pytest.approx((4.0, 3.0))


def test_a_tracker_that_does_not_answer_is_a_dropped_frame_not_a_hang():
    """The frame loop must return whether or not the tracker replied.

    A display that stops flipping because the eye tracker went quiet is a worse
    failure than a stale gaze sample: one loses a trial, the other loses the session
    and looks like a crashed rig.
    """
    from wl_xcon.eye import UdpSource

    # Nothing is listening on this port.
    source = UdpSource(host="127.0.0.1", port=9, timeout=0.01)
    source.open()
    try:
        assert source.poll(at=0.0) is None
    finally:
        source.close()


def test_closing_releases_the_socket_and_polling_again_is_refused():
    """A source that says it closed and did not leaks a descriptor per open.

    On a rig that is a session-length leak nobody sees until the process runs out,
    and polling a closed source must fail loudly rather than silently returning no
    gaze -- which reads as an animal not looking.
    """
    from wl_xcon.eye import UdpSource

    source = UdpSource(host="127.0.0.1", port=9, timeout=0.01)
    source.open()
    assert source._socket is not None
    source.close()

    assert source._socket is None
    with pytest.raises(RuntimeError, match="before open"):
        source.poll(at=0.0)
