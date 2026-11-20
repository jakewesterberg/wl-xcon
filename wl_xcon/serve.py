"""`wlx serve` -- the browser console's process (P4d-2b slices b1, b2a, b3a-2 and b2b).

Specs: `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md` §1-§5, and for
the rig's https page `docs/superpowers/specs/2026-10-02-p4d2b-b2b-remote-signin-design.md`.

**Its own process, beside `taskd` and never inside it** (S9a §7: the hot loop never
serves a request). It holds one `link.ZmqConsole`, keeps the latest frame, and serves
three things over the stdlib `ThreadingHTTPServer` -- the stack wl-preproc's responder
already runs, so no new dependency:

- `GET /` -- the page, every pane rendered in Python (`web.py`).
- `GET /events` -- server-sent events: one full render on connect, then the fragments
  that changed, once per frame this browser keeps up with and once per keepalive
  interval between frames, each re-rendered from a fresh snapshot. Every event
  carries `live` and `age` -- how long this process has held the latest frame, `null`
  before any -- which the page's stale timer runs on (Ruling 12, 2026-09-27).
- `GET /health` -- `health.py`'s body for wl-works, behind a bearer token.

- `POST /commands` (P4d-2b b2a, spec §5.3) -- one JSON command, validated before
  anything is queued (`parse_command`) and answered *sent*, *not delivered* or *busy*,
  the truth about delivery. On the plain-http listener it comes from the box's own page,
  under spec §2's four checks, and a command carrying a token is refused there. Since
  P4d-2b b3a-2 it also takes `wlx taskd`'s own four -- `open`, `check`, `start`, `end`
  -- built by the wire's own rules (`link._command_from`), as it builds a run's controls
  since engine build C2a (`clear`, `drum`, `training`), since C3 a setting handed back,
  a drawn range changed live and a revert (`hand_back`, `range`, `revert`), and since the
  pop-out search build a block moved on or back naming the rig's suggestion it confirms, and a
  hold of one (`next_block`, `back_block`, `decline`; `_WIRE_KINDS`), and since the console
  interface rework several changes applied together and a waiting change withdrawn
  (`apply_many`, `withdraw`), each naming its page's `cid`.
- `POST /gaze` (demo mode §4.5) -- one pointer report from a demo's page, **gated exactly as
  `/commands` is** (`_writer`, the write checks factored out of `_command`; §14 item 13), never
  by `may_write`, then checked (`parse_gaze`), and, while the latest frame is a demo session's
  and the page steers (`Steering`: one page at a time, until it releases the steer or is quiet
  for `STEER_HOLD_S`), packed as the rig reads it (`pointer.MESSAGE`) and pushed to the demo's
  gaze endpoint, `--link`'s fourth, with ZeroMQ's non-blocking send. **Each report costs a
  request**, and on the https page a token check too: stated, not measured.

**A demo's screen, drawn here** (demo mode §3.9, §4.4). A `link.Drawn` the telemetry thread
reads goes to `Hub.offer_drawn`, never `Hub.offer`; the hub's `demoscreen.Drawer` draws it with
the exact drawer on a thread of its own, never in the rig service's process, and each drawing
goes to every stream as its own server-sent event, `event: drawn`, in order, apart from the
frames, with the key list for that screen's keys (`web.demo_keys`, demo mode's Task 9); a stream
that connects is sent the latest. The page shows it only while the frame says `demo`, and only a
drawing of the session the frame is (`web`'s script).

**The rig's https page (b2b, `--https` and its five companion flags).** A second
listener, TLS, serves the same routes plus `POST /whoami` and `POST /signout`. A command
there is accepted from this rig's page (`Origin`, `Content-Type`) with a wl.works
member's token that `signin.Checker` accepts, offline, and is sent as that member's.
Without the flags there is no second listener and `signin` is never imported.

Everything else is 404 or 405, as JSON, never the stdlib's HTML page. **Every request
is answered only when its `Host` names this console** (spec §2, §5.3): on the plain-http
listener, loopback, the box's own names and addresses, and `--allow-host` names
(`box_names`); on the https listener, the rig page's own host, exactly. Anything else
gets a JSON 421 and no page, which closes DNS rebinding on the LAN-open reads too.

**Restarting it changes nothing in `taskd`** (spec §2): it reads the PUB socket, and
what it sends is acknowledged or said not to be; a pause, a schedule and every
setting are held by `taskd`, not here.

**Threads, and what each owns** (spec §2: each ZMQ socket has one owning thread).
The telemetry thread (`Server._listen`) owns a read-only `ZmqConsole`, its SUB
socket. The command thread (an `Outbox`) owns a `ZmqCommands`, the REQ socket, and
takes commands from a bounded queue. The mark thread (another `Outbox`) owns a
`ZmqMarks`, the PUSH socket to the session's mark endpoint, so a mark's signal goes
ahead of any command waiting on the rig's acknowledgment (spec §5.3). Given a gaze endpoint,
the gaze thread (a third `Outbox`) owns a `link.ZmqGaze`, the PUSH socket to a demo's gaze
endpoint (demo mode §4.5). The drawing thread (`demoscreen.Drawer`, started at a hub's first
`Drawn`) owns no socket: it draws, and hands each drawing to the hub. Each browser's
`/events` and each `POST` runs on the HTTP server's thread for that connection. With
`--https`, the https listener has a thread of its own, and each of its connections does
its TLS handshake on that connection's thread (`_PageServer`), and the keys thread
(`signin.Checker.keep_keys`) asks wl.works once `wlx serve` has bound, again every
`signin.RETRY_EVERY_S` until it has keys, then fetches the key set every
`signin.KEY_REFRESH_S` (b2b-ready §3.2-§3.3). A https setup that cannot be completed never
stops `wlx serve`: the https page is off, saying why (§3.1).

**No timing claim is made here.** `DEFAULT_STALE_AFTER_S` is a display choice (spec
§3); `QUEUE_DEPTH`, `RATE_SAMPLE_S`, `KEEPALIVE_S`, `REQUEST_TIMEOUT_S`, `RETRY_MS`,
`COMMAND_QUEUE_DEPTH`, `MARK_QUEUE_DEPTH`, `GAZE_QUEUE_DEPTH`, `BODY_LIMIT`, `MAX_EVENT_STREAMS`,
`MARKS_REMEMBERED`, `PAGES_REMEMBERED`, `PAGE_ID_LIMIT`, `OUTBOX_POLL_S` and the link's
`REPLY_TIMEOUT_S` and `CONNECT_TIMEOUT_S` are housekeeping, not a measurement of this system;
`STEER_HOLD_S` is the demo plan's call, with its reason where it is defined.
"""

from __future__ import annotations

import functools
import hmac
import ipaddress
import json
import math
import queue
import secrets
import socket
import ssl
import sys
import threading
import time
import traceback
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

from wl_xcon import actor as actors
from wl_xcon import demoscreen as _demoscreen
from wl_xcon import health as _health
from wl_xcon import link as _link
from wl_xcon import pointer as _pointer
from wl_xcon import web as _web
from wl_xcon import welfare as _welfare
from wl_xcon.actor import Actor, Box, Member

if TYPE_CHECKING:  # `signin` imports `jwt`; `serve` must import without it.
    from wl_xcon import signin as _signin

#: Seconds without a frame, while more are due, before the page greys and `/health`
#: says `degraded`. A display choice (spec §3), not a measurement.
DEFAULT_STALE_AFTER_S = 30.0
#: How many frames one browser's queue holds before its oldest is dropped (spec §2).
#: Small on purpose: telemetry is latest-wins, and a stream renders only the newest
#: frame it finds waiting (`Hub.take`).
QUEUE_DEPTH = 8
#: Trials per minute is read over the frames of the last five minutes (spec §4.1)...
RATE_WINDOW_S = 300.0
#: ...sampled at most once a second, so the window holds a few hundred points however
#: fast a simulator publishes.
RATE_SAMPLE_S = 1.0

#: What `Hub.take` returns once the hub is closed: the stream ends.
CLOSED = object()
#: What `Hub.take` returns when only a new drawing woke a stream (demo mode §4.4): the stream
#: sends the drawing, and no frame event.
DRAWN = object()
#: What a handler's write checks return once they have refused a request (`_writer`).
_REFUSED = object()


def _put_dropping_oldest(subscriber: queue.Queue, item: object) -> None:
    """Queue `item`, dropping the oldest item waiting if the queue is full (spec §2): a
    browser that falls behind loses its oldest frames, never the newest, and never
    holds up the thread that offers them."""
    while True:
        try:
            subscriber.put_nowait(item)
            return
        except queue.Full:
            try:
                subscriber.get_nowait()
            except queue.Empty:
                pass


def _wake(subscriber: queue.Queue) -> None:
    """Wake a stream to send the newest drawing (demo mode §4.4), **evicting nothing**: a full
    queue wakes its stream anyway, and every wake-up looks for a newer drawing, so a drawing never
    pushes out the frame or the `CLOSED` waiting there."""
    try:
        subscriber.put_nowait(DRAWN)
    except queue.Full:
        pass


class StreamsFull(Exception):
    """`Hub.subscribe` was asked for a stream past its `limit` (`MAX_EVENT_STREAMS`)."""


class Hub:
    """The latest frame, the rate window, and every open stream's queue (spec §2).

    `offer` and `reject` are called by the telemetry thread; everything else by HTTP
    handler threads. One lock guards the frame, the window and the table of
    subscribers; each queue is thread-safe on its own.

    **`offer` and `reject` assume one producer thread**, `Server._listen`, and are
    not safe to call from two at once: each copies the table of subscribers under the
    lock and pushes to the copy after releasing it. A `close()` that lands between
    the copy and the push can therefore leave one stale frame queued behind a
    stream's `CLOSED`. That is bounded -- one item per stream, from the one offer in
    flight -- and it cannot evict `CLOSED`: a queue holds `QUEUE_DEPTH` (8) items, so
    one more push drops only the oldest, and `take` returns `CLOSED` whenever it
    meets it.

    **One clock, and it is steady** (ledger Ruling 1, 2026-09-27). `steady` is what a
    frame is aged on -- `View.frame_age_s`, which the page's time since the last reward
    adds to the frame's own `wall_at` and `/health` reports as the last frame's age --
    and what the rate is read on. `welfare.steady_seconds` by default, which keeps
    counting while the host is asleep (P4d-2a I1), and injectable so that no test reads
    a real clock. **There is no wall clock here**: this process's host clock parts from
    a session's anchored one by any step it has taken since the session began, so
    nothing here subtracts it from a session instant.

    **A demo's screens are kept apart from its frames** (demo mode §3.9, §4.4). `offer_drawn`,
    on the telemetry thread, hands each `link.Drawn` to the hub's `demoscreen.Drawer`, made at
    the first and closed with the hub, which draws on its own thread and gives each drawing to
    `_drawn`: kept as the latest, numbered, and every stream woken (`_wake`) to send it as its
    own event. A drawing never enters the frame, the rate window or `/health`.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        steady: Callable[[], float] = _welfare.steady_seconds,
        marks: bool = False,
        gaze: bool = False,
    ) -> None:
        #: The PUB endpoint the telemetry thread reads, handed to every `View` so a
        #: page with no frame names where it is listening (m4). No default: a hub
        #: that did not know it would have the page guess.
        self._endpoint = endpoint
        #: Whether this console has the session's mark endpoint (P4d-2b b2a), for
        #: every `View`: without it the page greys its mark control.
        self._marks = marks
        #: Whether this console has a demo's gaze endpoint (`--link`'s fourth; demo mode §4.5),
        #: for every `View`: without it no page steers a demo here.
        self._gaze = gaze
        self._steady = steady
        self._lock = threading.Lock()
        self._frame: _link.Telemetry | _link.Idle | None = None
        #: When `_frame` arrived, on `steady`.
        self._received: float | None = None
        #: `(steady, trial_index)` sampled at most every `RATE_SAMPLE_S`, within
        #: `RATE_WINDOW_S` of the newest frame.
        self._points: deque = deque()
        #: The newest frame's `(steady, trial_index)`, sampled or not.
        self._newest: tuple[float, int] | None = None
        self._rejected: str | None = None
        #: Each open stream's queue, and whether it is on the box.
        self._subscribers: dict[queue.Queue, bool] = {}
        self._closed = False
        #: The thread a demo's screens are drawn on, made at the first `Drawn`; `None` before.
        self._drawer: _demoscreen.Drawer | None = None
        #: The latest drawing, `(its number, its SVG)`, counted from 1; `(0, None)` before any.
        self._drawing: tuple[int, str | None] = (0, None)
        #: The latest drawing's keys, `Drawn.keys` (key `k`'s input at index `k - 1`), which the
        #: page's key list names beside B (demo mode §3.4, §4.3); `()` before any.
        self._drawing_keys: tuple = ()

    def offer(self, frame: _link.Telemetry | _link.Idle) -> None:
        """Keep `frame` as the latest and hand it to every open stream.

        The rate window restarts when the session changes or its trial count goes
        back: a new `wlx run` on the same link is a new session, and a rate across two
        would describe neither. An `Idle` frame is held like any other and empties the
        rate window; a new run, whose trial count starts again, restarts it too. A good
        frame clears a refusal (`reject`).
        """
        now = self._steady()
        with self._lock:
            previous = self._frame
            if isinstance(frame, _link.Idle):
                # No session, so no trials and no rate (P4d-2b spec §6.1).
                self._points.clear()
                self._newest = None
            else:
                if (
                    previous is None
                    or isinstance(previous, _link.Idle)
                    or previous.session_id != frame.session_id
                    or frame.trial_index < previous.trial_index
                ):
                    self._points.clear()
                if not self._points or now - self._points[-1][0] >= RATE_SAMPLE_S:
                    self._points.append((now, frame.trial_index))
                while now - self._points[0][0] > RATE_WINDOW_S:
                    self._points.popleft()
                self._newest = (now, frame.trial_index)
            self._frame, self._received, self._rejected = frame, now, None
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, frame)

    def reject(self, why: str) -> None:
        """Say that a frame arrived and could not be used, and wake every stream to
        show it (`Server._listen`). The last good frame stays: a console that cannot
        read one frame shows what it last could, beside the reason -- never a guess."""
        with self._lock:
            self._rejected = why
            latest = self._frame
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, latest)

    def offer_drawn(self, drawn: _link.Drawn) -> None:
        """**A demo's screen, to be drawn** (demo mode §3.9, §4.4), from the telemetry thread:
        handed to the hub's `demoscreen.Drawer`, made here at the first, which draws the newest
        screen waiting once the drawing in progress is done. Never a frame: `offer` never sees
        it. Dropped once the hub is closed."""
        with self._lock:
            if self._closed:
                return
            if self._drawer is None:
                self._drawer = _demoscreen.Drawer(self._drawn)
            drawer = self._drawer
        drawer.offer(drawn)

    def _drawn(self, drawn: _link.Drawn, svg: str) -> None:
        """One drawing done, on the drawing thread: kept as the latest under the next number,
        and every stream woken to send it (`_wake`)."""
        with self._lock:
            if self._closed:
                return
            self._drawing = (self._drawing[0] + 1, svg)
            self._drawing_keys = tuple(drawn.keys)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            _wake(subscriber)

    def drawing(self) -> tuple[int, str | None]:
        """The latest drawing, `(its number, its SVG)`, numbered from 1 in the order drawn, so a
        stream sends one only when it is newer than the last it sent; `(0, None)` before any."""
        with self._lock:
            return self._drawing

    def drawing_and_keys(self) -> tuple[int, str | None, tuple]:
        """`drawing()` and the keys of the screen it drew (`Drawn.keys`), read together, so the
        key list a stream sends beside a drawing is that drawing's."""
        with self._lock:
            return (*self._drawing, self._drawing_keys)

    def demo_running(self) -> bool:
        """**Whether the latest frame is a demo session's** (`Telemetry.demo`; demo mode §4.5),
        the one a page steers. An idle frame is no session's, a demo service's included."""
        with self._lock:
            latest = self._frame
        return isinstance(latest, _link.Telemetry) and latest.demo

    def _rate(self) -> float | None:
        """Trials per minute over the window. The caller holds the lock."""
        if not self._points or self._newest is None:
            return None
        (t0, n0), (t1, n1) = self._points[0], self._newest
        if t1 <= t0:
            return None
        return 60.0 * (n1 - n0) / (t1 - t0)

    def trials_per_min(self) -> float | None:
        """Derived here, from `trial_index` and when frames arrived (spec §4.1); `None`
        until two frames a moment apart exist. **Bounds nothing**, and the page says
        it is derived."""
        with self._lock:
            return self._rate()

    def snapshot(
        self,
        *,
        on_box: bool,
        stale_after_s: float,
        can_write: bool = False,
        signin: bool = False,
        https_page: bool = False,
        streams_max: int | None = None,
    ) -> tuple[_link.Telemetry | _link.Idle | None, _web.View]:
        """The latest frame and the `View` a render of it needs, read together. The
        frame's age is on `steady` alone (ledger Ruling 1). `can_write` is the
        handler's to say (P4d-2b b2a, `may_write`); a caller that does not say gets a
        view that may not write."""
        now = self._steady()
        with self._lock:
            latest = self._frame
            age = None if self._received is None else now - self._received
            rate = self._rate()
            lan = sum(1 for box in self._subscribers.values() if not box)
            streams = len(self._subscribers)
            rejected = self._rejected
        return latest, _web.View(
            frame_age_s=age,
            stale_after_s=stale_after_s,
            trials_per_min=rate,
            on_box=on_box,
            lan_viewers=lan,
            rejected=rejected,
            endpoint=self._endpoint,
            can_write=can_write,
            can_mark=self._marks,
            can_gaze=self._gaze,
            signin=signin,
            https_page=https_page,
            streams=None if streams_max is None else (streams, streams_max),
        )

    def subscribe(self, *, on_box: bool, limit: int | None = None) -> queue.Queue:
        """A new stream's bounded queue. After `close`, one that is already closed.
        Raises `StreamsFull` when `limit` streams are already open: counted under the
        lock that adds one, so two connections at the limit cannot both get in. The
        count changes only here and in `unsubscribe`, on a connect and a close."""
        subscriber: queue.Queue = queue.Queue(maxsize=QUEUE_DEPTH)
        with self._lock:
            if self._closed:
                subscriber.put_nowait(CLOSED)
                return subscriber
            if limit is not None and len(self._subscribers) >= limit:
                raise StreamsFull(limit)
            self._subscribers[subscriber] = on_box
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            self._subscribers.pop(subscriber, None)

    def viewers(self) -> tuple[int, int]:
        """How many streams are open: `(on the box, from the LAN)`."""
        with self._lock:
            box = sum(1 for on in self._subscribers.values() if on)
            return box, len(self._subscribers) - box

    def take(self, subscriber: queue.Queue, timeout: float) -> object:
        """The newest item waiting on `subscriber` -- a frame, `None` when a refusal
        woke it before any frame arrived, `DRAWN` when only a new drawing did, or
        `CLOSED` -- waiting up to `timeout` seconds and raising `queue.Empty` after that.

        **Older frames are skipped, not rendered**: telemetry is latest-wins, so a
        browser that fell behind catches up in one render rather than replaying what
        it missed. **A frame outranks a drawing** (demo mode §4.4): `DRAWN` is returned
        only when no frame was waiting, so a drawing never hides a frame's wake-up, and
        the stream looks for a newer drawing after every wake-up either way.
        """
        item = subscriber.get(timeout=timeout)
        while item is not CLOSED:
            try:
                later = subscriber.get_nowait()
            except queue.Empty:
                break
            if later is not DRAWN or item is DRAWN:
                item = later
        return item

    def close(self) -> None:
        """End every open stream, and any opened after this. The table is emptied so
        no later frame can push a stream's `CLOSED` out of its queue. The drawing thread
        finishes the drawing in progress, keeps nothing more, and ends (`Drawer.close`),
        outside the lock its last drawing asks for."""
        with self._lock:
            self._closed = True
            subscribers = list(self._subscribers)
            self._subscribers.clear()
            drawer, self._drawer = self._drawer, None
        for subscriber in subscribers:
            _put_dropping_oldest(subscriber, CLOSED)
        if drawer is not None:
            drawer.close()


#: Seconds between refreshes on a stream with no frame to send: an event re-rendered
#: from a fresh snapshot, so what ages between frames -- the time since the last
#: reward, *wl-works sees*, `age` -- moves on the page (Ruling 12, 2026-09-27). Also
#: housekeeping: a browser that went away is found at the next write rather than never.
KEEPALIVE_S = 15.0
#: The reconnection delay the page's `EventSource` is told, in milliseconds --
#: housekeeping, not a measurement of this system.
RETRY_MS = 3000
#: Socket timeout for every request -- wl-preproc's `_REQUEST_TIMEOUT_S`, for its
#: reason: a request that never finishes must not park a thread for good.
#: Housekeeping, not a measurement of this system.
REQUEST_TIMEOUT_S = 30.0
#: The most `/events` streams open at once, on both listeners together; one past it is
#: answered 503 (XC-043). **An engineering default, not a measurement and not in the spec
#: (b1's spec and plan state no count of consoles):** the lab opens about four pages of
#: one rig's console at once (the rig PC's own, a lab member's, wl-works', one spare), and
#: a reload leaves its old stream open until this process next writes to it and finds the
#: browser gone, up to `KEEPALIVE_S` later, so four times that, 16. A stream is a thread
#: and a socket; this keeps a runaway page from taking the process, never a page from
#: the lab. Awaiting the controller's ruling.
MAX_EVENT_STREAMS = 16

#: Each bundled font by the exact path the page asks for it at (`web.FONTS`). A request
#: is looked up here, never joined onto a directory, so there is no path to traverse.
_FONTS = {f"/fonts/{font.file}": font for font in _web.FONTS}
# `/whoami` and `/signout` are not here: they answer 404 to every method on the http
# listener (b2b spec §3). Task 9 of the b2b plan routes them on https.
_ROUTES = frozenset({"/", "/events", "/health", "/commands", "/gaze", *_FONTS})
#: The paths a `POST` writes to, which a 405 names as allowing `POST` alone.
_WRITES = frozenset({"/commands", "/gaze"})
#: What a command carrying a token to the plain-http listener is told (b2b spec §3).
TOKEN_OVER_HTTP = "sign-in works only on the rig's https page"
#: What the https page hears for a write that did not come from its own page (b2b spec §3).
FROM_THE_PAGE = "a request must come from this rig's page"
#: What `POST /signout` answers (b2b spec §4).
SIGNED_OUT_HERE = "signed out at this rig"
_UNAUTHORIZED = {"error": "unauthorized"}
#: What a request whose `Host` does not name this console is answered (P4d-2b spec
#: §5.3): a JSON 421 and no page. It names no host, echoing nothing it was sent.
_MISDIRECTED = {
    "error": "misdirected request",
    "said": (
        "this console answers only to its own names: loopback, this box's host names "
        "and addresses, and names given with --allow-host"
    ),
}
#: Fixed bodies, keyed on the status alone and echoing nothing a caller sent
#: (wl-preproc's `_SEND_ERROR_BODIES`).
_ERRORS = {
    400: {"error": "bad request"},
    404: {"error": "not found"},
    405: {"error": "method not allowed"},
    414: {"error": "request line too long"},
    431: {"error": "request header fields too large"},
    #: A handler that raised (`_backstop`): what failed is logged, never sent (XC-042).
    500: {"error": "internal server error"},
    505: {"error": "http version not supported"},
}
_FALLBACK = {"error": "request rejected"}
#: What a stream past `MAX_EVENT_STREAMS` is answered. An `EventSource` cannot read it: the
#: page sees its stream fail, says *stream lost* and asks again after `RETRY_MS`, by which
#: time a closed page's slot may be free.
_STREAMS_FULL = {
    "error": "too many streams open",
    "said": "this console already has as many pages open as it serves; close one and reload",
}


def on_box(host: str) -> bool:
    """Whether a peer is this machine: loopback in either family, or an IPv4 loopback
    mapped into IPv6. Anything that does not parse is the LAN."""
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


#: The names loopback goes by in a `Host` header (P4d-2b spec §2, §5.3).
LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def host_name(header: str | None) -> str | None:
    """The name a `Host` header gives, lowercased and without its port, or `None`
    when there is none or it does not parse: `127.0.0.1:8080` is `127.0.0.1`,
    `[::1]:8080` is `::1`, `Box.local` is `box.local`. An unbracketed IPv6
    address is not a `Host` (RFC 9110 §7.2 brackets it) and names nothing here."""
    if not header or not header.isascii():
        return None
    value = header.strip().lower()
    if value.startswith("["):
        name, bracket, rest = value[1:].partition("]")
        if not bracket or not name:
            return None
        if rest and not (rest.startswith(":") and rest[1:].isdecimal()):
            return None
        return name
    name, colon, port = value.rpartition(":")
    if not colon:
        return value or None
    if not port.isdecimal() or not name or ":" in name:
        return None
    return name


def names_loopback(name: str | None) -> bool:
    """Whether a `Host` name is this machine by loopback (spec §2's second check):
    `localhost`, or an address in 127.0.0.0/8 or `::1`."""
    if name is None:
        return False
    return name == "localhost" or on_box(name)


def box_names(allowed: tuple[str, ...] = ()) -> frozenset[str]:
    """Every name a request's `Host` may give for this console (P4d-2b spec §5.3):
    loopback, this box's host name and fully qualified name, the addresses those
    resolve to, and `allowed` -- `--allow-host`, for a name the box is reached by
    that it does not know itself by. Lowercased.

    Read once, when `wlx serve` starts. A lookup that fails adds nothing and is not
    an error: loopback and `--allow-host` still work, and the refusal a LAN viewer
    then gets names the flag that fixes it."""
    names = set(LOOPBACK_NAMES)
    for name in (socket.gethostname(), socket.getfqdn()):
        if name:
            names.add(name.lower())
    for name in sorted(names - LOOPBACK_NAMES):
        try:
            found = socket.getaddrinfo(name, None)
        except OSError:
            continue
        names.update(info[4][0].split("%", 1)[0].lower() for info in found)
    names.update(name.strip().lower() for name in allowed if name.strip())
    return frozenset(names)


def _console_at(host: str, port: int, name: str) -> str:
    """Where a person opens the page bound at `host:port`, for `wlx serve`'s startup
    line (XC-045). A bind on one address is its own URL. The wildcard, `0.0.0.0`, is no
    address a browser can open, so it is never printed as one: the line names this box
    by `name`, its host name (`run` passes `socket.gethostname()`, which asks the
    system and not the network, and which `box_names` answers to), and `localhost` for
    this box itself, and says the page listens on all interfaces. A name that is empty,
    names loopback or is not ASCII -- a browser sends that one punycoded, which the
    `Host` check does not know -- is no URL for another machine: `localhost` alone.
    Loopback is `names_loopback`'s, or a name it does not know: one beginning
    `localhost.`, such as RHEL's `localhost.localdomain`, or one in `.localhost`, which
    RFC 6761 §6.3 reserves for loopback (UNVERIFIED: recalled, not re-read, 2026-10-31)."""
    try:
        wildcard = ipaddress.ip_address(host).is_unspecified
    except ValueError:
        wildcard = False
    if not wildcard:
        return f"http://{host}:{port}/"
    local = f"http://localhost:{port}/"
    lowered = name.lower()
    loopback = (
        names_loopback(lowered)
        or lowered.startswith("localhost.")
        or lowered.endswith(".localhost")
    )
    if name and name.isascii() and not loopback:
        return f"http://{name}:{port}/ (listening on all interfaces; {local} on this box)"
    return (
        f"{local} on this box (listening on all interfaces; from another machine, use "
        f"this box's name or address)"
    )


def event(payload: dict, *, name: str = "frame") -> bytes:
    """One server-sent event named `name`: `frame`, or since demo mode `drawn`, a demo's
    screen drawn (§4.4), its own kind so a page never takes one for the other. `json.dumps`
    escapes every newline and control character, so the payload is one `data:` line
    whatever telemetry held."""
    return f"event: {name}\ndata: ".encode("ascii") + json.dumps(payload).encode("utf-8") + b"\n\n"


def _csp(nonce: str, connect: str = "") -> str:
    """The page's Content-Security-Policy: its one script by nonce, inline styles (the
    bar widths), its bundled fonts and the event stream from this origin, and nothing
    else. Defense beneath `web._e`, not instead of it. `connect` is one more origin the
    page may `fetch`: on the https page, wl.works' token endpoint (b2b spec §3), the one
    place a request from that page goes besides this rig. From the box's own page, no
    request leaves the box. **Images from `data:` alone** (demo mode §4.4): a demo's drawing
    carries each eye's frame as a PNG inside its SVG (`demoscreen.render`), and no image is
    fetched from anywhere."""
    sources = f"'self' {connect}" if connect else "'self'"
    return (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
        f"font-src 'self'; img-src data:; connect-src {sources}; base-uri 'none'; "
        f"form-action 'none'; frame-ancestors 'none'"
    )


# --- writes from the box (P4d-2b b2a, spec §5.3) ---------------------------------------

#: The largest body `POST /commands` reads, in bytes. One command is a few hundred;
#: a longer body is refused before it is read. Housekeeping, not a measurement.
BODY_LIMIT = 4096
#: The most a refusal on the https page reads and discards of a body it will not use.
#: Housekeeping, not a measurement.
REFUSAL_DRAIN_LIMIT = 65536
#: The longest a refusal spends reading that body, in seconds, however slowly it arrives.
#: `REQUEST_TIMEOUT_S` bounds one `recv`, so a client dripping a byte every few seconds
#: could otherwise hold its thread for as long as it keeps dripping; past this the refusal
#: is sent anyway and the connection closed. An engineering default, not a measurement:
#: a page's few hundred bytes on a LAN take far less.
REFUSAL_DRAIN_S = 5.0
#: The longest name a person may give at the box's prompt (spec §5.2).
NAME_LIMIT = 64
#: The largest mark number `wlx serve` hands a browser: 2**53 - 1, JavaScript's
#: `Number.MAX_SAFE_INTEGER`, the largest whole number a browser's JSON carries
#: exactly -- the page sends the number back with the note, and a number it had
#: rounded would join nothing. Within the signal's eight bytes (`link.MARK_LIMIT`).
MARK_ID_LIMIT = 2**53 - 1
#: How many marks' instants `wlx serve` keeps for the notes that follow them. A mark
#: whose note comes after 256 later marks, or after a restart, is recorded with its
#: pressed and received instants unknown, never guessed. Housekeeping, not a
#: measurement of this system.
MARKS_REMEMBERED = 256
#: How many commands may wait for the command thread, and marks for the mark thread,
#: before `POST /commands` answers *busy* (spec §5.3). Housekeeping, not a
#: measurement: a person's clicks, debounced, do not fill them; a flood does.
COMMAND_QUEUE_DEPTH = 4
MARK_QUEUE_DEPTH = 8
#: How long an outbox thread waits for work before it looks again at whether to
#: stop, so `Server.close` returns promptly. A responsiveness choice, not a
#: measurement of this system.
OUTBOX_POLL_S = 0.25

#: What the page is told when the rig has a command (spec §5.3): *sent* means `taskd`
#: acknowledged receipt. Whether it was applied or refused is the feed's to show.
SENT = (
    "sent: the rig has it and acts on it at its next trial boundary; the changes feed "
    "shows what it did"
)
#: What the page is told when the queue is full (spec §5.3).
BUSY = (
    503,
    {
        "status": "busy",
        "said": (
            "busy: wlx serve is still sending earlier commands, so this one was not "
            "sent; try again"
        ),
    },
)
#: What the page is told when the rig has a manual reward (PI, 2026-09-28). Whether
#: it was given, and how much, is the changes feed's and the fluid total's to show.
REWARD_SENT = (
    "sent: the rig has the reward command; the changes feed and the fluid total show "
    "whether it was given"
)
#: What the page is told when the rig took a manual reward and did not acknowledge it
#: (PI, 2026-09-28: no accidental doubles). It may have been given, so it is neither
#: *not delivered*, which would invite a second press, nor sent again.
REWARD_UNKNOWN = (
    504,
    {
        "status": "unknown",
        "said": (
            "unknown: the rig took the reward command and did not acknowledge it, so "
            "whether the reward was given is not known, and it was not sent again; "
            "check the session's fluid total before pressing again"
        ),
    },
)

#: What the page is told when the rig has one of `wlx taskd`'s own commands -- an open,
#: a check, a start or an end (P4d-2b b3a-2): what it did is the page's to show from
#: the frames that follow, as a session, a pre-flight, a run, the question a far mark
#: raises, or a refusal with its sentence. `SENT`'s "at its next trial boundary" is a
#: run's command's, and not true of an open between runs.
SERVICE_SENT = (
    "sent: the rig has it; the page shows what it did -- a session, a pre-flight, a run, "
    "a question to answer, or a refusal with its reason"
)


class BadCommand(ValueError):
    """A `POST /commands` body that is not a command this console sends. The message
    is the sentence the page shows; nothing was queued."""


@dataclass(frozen=True, slots=True)
class MarkSignal:
    """M pressed at the box: send the mark's signal now, ahead of every command (spec
    §5.3). `pressed_at` is the browser's clock, `None` if it did not say."""

    by: Actor
    pressed_at: float | None


@dataclass(frozen=True, slots=True)
class MarkNote:
    """The note typed after M -- empty after Esc -- for mark `mark`: sent to the rig as
    a `link.Mark` command, with the instants `wlx serve` kept for that mark."""

    mark: int
    note: str
    by: Actor


#: The fields each kind of command takes besides `kind` and `by`. A schedule takes
#: exactly one of `at`, `trials` or `ml`, checked in `parse_command`.
_SHAPES = {
    "set": frozenset({"name", "value"}),
    "stop": frozenset(),
    "pause": frozenset(),
    "resume": frozenset(),
    "cancel": frozenset(),
    "reward": frozenset(),
    "schedule": frozenset({"at", "trials", "ml"}),
    "mark": frozenset({"pressed_at"}),
    "note": frozenset({"mark", "note"}),
    # P4d-2b b3a-2: `wlx taskd`'s own, by the wire's field names (`link._command_from`).
    # And since demo mode's Task 9 whether the session is a demo (`link.OpenSession.demo`).
    "open": frozenset({
        "session_id", "animal", "deployment", "view", "session_kind", "departure",
        "delivered_today", "answer", "amend_to", "amend_reason", "accepted", "demo",
    }),
    # The block of the plan a run starts at: the pop-out search build's Task 6.
    "check": frozenset({"task", "values", "plan", "start_block"}),
    "start": frozenset({"task", "values", "trials", "acknowledged", "plan", "start_block"}),
    "end": frozenset({"session_id", "returned", "confirm"}),
    "resume_session": frozenset({"session_id"}),
    # Engine build C2a: a run's count and its drumming (the PI, 2026-10-11).
    "clear": frozenset({"condition", "rest"}),
    "drum": frozenset({"scope"}),
    # The PI, 2026-10-18: the training aid *clear* and the percentage setting, switched.
    "training": frozenset({"setting", "on"}),
    # The console settings build's Task 10 (the design's §8): the training switch, on, frozen or
    # the plan's full task (`link.Shaping`).
    "shaping": frozenset({"position"}),
    # Engine build C2b (the PI, 2026-10-19): a run moved on a block, or back one, by hand; since
    # the pop-out search build (2026-11-07) naming the rig's suggestion it confirms, where it
    # answers one, and the trainer's hold of one (`decline`; "Rig suggests, trainer confirms").
    "next_block": frozenset({"suggestion"}),
    "back_block": frozenset({"suggestion"}),
    "decline": frozenset({"suggestion"}),
    # Engine build C3 (the PI, 2026-10-30, Q7a and Q7b; TSK-43): a setting handed back, a drawn
    # range changed live, and the run reverted to an earlier moment, by the wire's field names.
    "hand_back": frozenset({"name"}),
    "range": frozenset({"name", "numbers"}),
    "revert": frozenset({"change"}),
    # The console settings build (the PI, 2026-11-16): a timing setting switched to drawn on its
    # card, a person's draw of one of its shapes (`link.SetForm`).
    "form": frozenset({"name", "shape", "numbers", "values", "weights"}),
    # And a color setting's hue picked by its set on its card (`link.SetColor`; the design's §6).
    "color": frozenset({"name", "colorset", "color"}),
    # And one of a setting's declared choices picked on its box by its words (`link.SetChoice`; the
    # pop-out revision's Task 5b: a look's shape is a console setting).
    "choice": frozenset({"name", "choice"}),
    # And a new color defined three ways, saved as its set's proposed file (`link.DefineColor`; the
    # design's §6, the build's Task 8).
    "define_color": frozenset({"colorset", "new_set", "name", "method", "numbers"}),
    # The console interface rework's Task 4 (the PI, 2026-11-19, "Apply per box, plus Apply all",
    # and "Yes, a withdraw button"): several changes applied together, each a `set`, `range`,
    # `form`, `color` or `choice` by its own fields (`_APPLIED`), and a waiting act withdrawn by its
    # `cid`.
    "apply_many": frozenset({"changes"}),
    "withdraw": frozenset(),
}
#: **The kinds one change of an `apply_many` may be**, each by the fields its own command takes
#: (`_SHAPES`), its `kind` among them, and never a `by` or a `cid`: the act's are the command's.
_APPLIED = {kind: _SHAPES[kind] | {"kind"} for kind in _link.APPLY_KINDS}
_SCHEDULES = {"at": "clock", "trials": "trials", "ml": "fluid"}
#: The kinds `wlx taskd` takes (open, check, start, end and resume_session) that the page sends by the wire's own field names, built
#: by the wire's own function (`link._command_from`; the b3a-2 plan, decision 3).
_SERVICE_KINDS = frozenset({"open", "check", "start", "end", "resume_session"})

#: The kinds the page sends by the wire's own field names and builds by the wire's own function
#: (`link._command_from`): the service's, since engine build C2a a run's `clear`, `drum` and
#: `training`, since C3 its `hand_back`, `range` and `revert`, and since the pop-out search build
#: `next_block`, `back_block` and `decline`, whose `suggestion` the wire checks
#: (`link._suggestion`), which go to the run as any control does, and since the console settings
#: build `form`, `color`, `define_color` and `shaping`, since the console interface rework
#: `apply_many` and `withdraw`, and since the pop-out revision's Task 5b `choice`. A range's
#: numbers, a form's numbers, values and weights, and a new color's numbers, are decoded there by
#: `link._setting`, as a setting's value is; a color's set and hue, and a choice's words, are words
#: (`link._word`).
_WIRE_KINDS = _SERVICE_KINDS | {"clear", "drum", "training", "hand_back", "range", "revert",
                                "next_block", "back_block", "decline", "form", "color", "choice",
                                "define_color", "shaping", "apply_many", "withdraw"}


def _finite(value: int | float) -> bool:
    """`math.isfinite`, except a Python `int` too large to become a `float` at all
    (`10**400`, say) is "not finite" too, rather than the `OverflowError`
    `math.isfinite` itself raises for one (fix round 1, security review Important
    2): msgpack cannot carry an int that large, but a `POST /commands` JSON body
    can, and `parse_command` must answer with a refusal here, never raise."""
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _person(by: object) -> Box:
    """The actor a box command is recorded under: the name the page asked for, as a
    `Box`, which prints as `NAME (box, unverified)` (spec §2, S9a §6: a forgeable name
    is worse than none, because it is believed, so it says it is unverified; b2b spec
    §6)."""
    if (
        not isinstance(by, str)
        or not by.strip()
        or len(by.strip()) > NAME_LIMIT
        or not by.strip().isprintable()
    ):
        raise BadCommand(
            f"every command records who sent it (S9a §6): give a name of 1 to "
            f"{NAME_LIMIT} printable characters"
        )
    return Box(by.strip())


#: The query fields `GET /color-preview` reads besides a method's numbers.
_PREVIEW_FIELDS = ("set", "method")


def _frame_sets(frame) -> dict:
    """**Each color set a telemetry frame's cards describe**, by name, as a `colordef.Frame`: its
    apex, luminance, design and hues' chromaticities as the rig sent them (`ParamRow.color`'s
    `sets`). Empty for an idle frame, or none."""
    from wl_xcon import colordef

    found: dict = {}
    for row in getattr(frame, "params", ()) or ():
        sets = (row.color or {}).get("sets") if isinstance(row.color, dict) else None
        for name, entry in (sets or {}).items():
            if name in found or not isinstance(entry, dict):
                continue
            hues = entry.get("hues") if isinstance(entry.get("hues"), dict) else {}
            found[name] = colordef.Frame(
                name=name, apex=tuple(entry["apex"]),
                luminance_cd_m2=float(entry["luminance_cd_m2"]),
                design=dict(entry["design"]) if isinstance(entry.get("design"), dict) else None,
                colors={hue: tuple(at["xy"]) for hue, at in hues.items()
                        if isinstance(at, dict) and "xy" in at})
    return found


def color_preview(frame, query: dict) -> tuple[int, dict]:
    """**`GET /color-preview`'s answer** (the console settings design's §6; its plan's Task 8): a new
    color's chromaticity by `colordef.chromaticity`, in the set the latest frame's cards describe by
    `set` (`_frame_sets`), or a new set's frame (`colordef.new_set`) for a name none describes, by
    `method` and its numbers, each a query field holding one number. `{"x", "y", "srgb", "in_srgb",
    "said"}`: x and y as the set's file would write them (`colordef.written`), which is what the rig
    saves for the same numbers in the same set; its swatch on the sRGB standard at the set's
    luminance and whether the standard shows it there (`colordef.swatch`), approximate on any
    screen not measured; and a sentence. **Refused** (400, the numbers `None` and `said` why) for a
    method, a number or a frame that defines no color. It writes nothing, so any viewer may ask."""
    from wl_xcon import colordef

    def refused(why: str) -> tuple[int, dict]:
        return 400, {"x": None, "y": None, "srgb": None, "in_srgb": None, "said": why}

    if any(len(values) != 1 for values in query.values()):
        return refused("each field of a color preview is given once")
    given = {key: values[0] for key, values in query.items()}
    named, method = given.get("set", ""), given.get("method", "")
    numbers = {}
    for key, value in given.items():
        if key in _PREVIEW_FIELDS:
            continue
        try:
            number = float(value)
        except ValueError:
            return refused(f"a new color's {key} is {value!r}, not a number")
        if not math.isfinite(number):
            return refused(f"a new color's {key} is {value!r}, not a finite number")
        numbers[key] = number
    try:
        within = _frame_sets(frame).get(named) or colordef.new_set(named, method, numbers)
        x, y = colordef.written(colordef.chromaticity(within, method, numbers))
        srgb, inside = colordef.swatch(within, (x, y))
    except (ValueError, KeyError, TypeError) as why:
        return refused(str(why))
    outside = "" if inside else (", outside what the sRGB standard shows at the set's luminance, "
                                 "so a panel like it desaturates the set to show it")
    said = (f"{colordef.SAID[method]} ({colordef.numbers_words(method, numbers)}) in {named}: "
            f"x {x:.5f}, y {y:.5f}{outside}; the swatch is approximate: this screen is not "
            f"measured")
    return 200, {"x": x, "y": y, "srgb": srgb, "in_srgb": inside, "said": said}


def parse_command(data: object, actor: Member | None = None):
    """One `POST /commands` body -- a JSON object with a `kind` and the person's
    name, `by` -- as what `Server.dispatch` sends: a `link` command, a `MarkSignal`
    or a `MarkNote`. **Validated before anything is queued** (spec §5.3), with the
    wire's own rules where the wire has one (`link._setting` for a value, M8;
    `link.check_schedule` for a schedule), so the page hears the sentence at once
    and the rig never sees what it would refuse on type. Raises `BadCommand`.

    A field a kind does not take is refused, not ignored: a page that sent one has a
    bug a person should see.

    **From a signed-in page (b2b spec §3)** `actor` is the member `signin` named, and
    the body carries no `by`: who sent it is the sign-in's, never what a page wrote."""
    if not isinstance(data, dict):
        raise BadCommand("a command is one JSON object")
    kind = data.get("kind")
    # `isinstance` first (fix round 1, Important 2): `kind not in _SHAPES` alone
    # raises `TypeError: unhashable type` for a `kind` that is a `list` or a
    # `dict`, and `isinstance(kind, str)` being `False` short-circuits `or` before
    # that membership test ever runs.
    if not isinstance(kind, str) or kind not in _SHAPES:
        raise BadCommand(f"{kind!r} is not a command this console sends")
    if actor is None:
        by = _person(data.get("by"))
        allowed = {"kind", "by"}
    else:
        if "by" in data:
            raise BadCommand(
                "a command from a signed-in page takes no by; who sent it is the sign-in's"
            )
        by = actor
        allowed = {"kind"}
    if kind in _link.CID_KINDS:
        # **A box's command id rides beside the command** (schema 23; the console interface
        # design's goal 4): the page's own name for the press, which the verdict echoes, decoded
        # by the wire's rule (`link._cid`), never as a value.
        allowed |= {"cid"}
    extra = set(data) - allowed - _SHAPES[kind]
    if extra:
        raise BadCommand(f"a {kind} command takes no {', '.join(sorted(extra))}")
    if kind == "apply_many" and isinstance(data.get("changes"), list):
        # Each change by its own kind's fields, as a command of that kind is refused one it does
        # not take; what each is, and how many, the wire's rule says (`link._changes`).
        for change in data["changes"]:
            named = change.get("kind") if isinstance(change, dict) else None
            taken = _APPLIED.get(named) if isinstance(named, str) else None
            if taken is not None and set(change) - taken:
                raise BadCommand(f"a {change['kind']} change in an apply_many takes no "
                                 f"{', '.join(sorted(set(change) - taken))}")
    if kind in _WIRE_KINDS:
        try:
            return _link._command_from({**data, "by": actors.to_map(by)})
        except _link.CommandRefused as refused:
            raise BadCommand(refused.why) from refused
    if kind == "set":
        name = data.get("name")
        if not isinstance(name, str) or not name or len(name) > _link.TEXT_LIMIT:
            raise BadCommand("a setting names its parameter")
        try:
            value = _link._setting(data.get("value"), name, by)
            cid = _link._cid(data, kind, by)
        except _link.CommandRefused as refused:
            raise BadCommand(refused.why) from refused
        return _link.SetParameter(name=name, value=value, by=by, cid=cid)
    if kind == "schedule":
        given = [key for key in _SCHEDULES if key in data]
        if len(given) != 1:
            raise BadCommand("a scheduled stop takes exactly one of at, trials or ml")
        stop, value = _SCHEDULES[given[0]], data[given[0]]
        why = _link.check_schedule(stop, value)
        if why is not None:
            raise BadCommand(why)
        return _link.ScheduleStop(kind=stop, value=value, by=by)
    if kind == "mark":
        pressed = data.get("pressed_at")
        if pressed is not None and (
            isinstance(pressed, bool)
            or not isinstance(pressed, (int, float))
            or not _finite(pressed)
        ):
            raise BadCommand("a mark's pressed_at is the browser's clock, in seconds")
        return MarkSignal(by=by, pressed_at=None if pressed is None else float(pressed))
    if kind == "note":
        number, note = data.get("mark"), data.get("note")
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= MARK_ID_LIMIT
        ):
            raise BadCommand("a note names the mark it is for")
        if not isinstance(note, str) or len(note) > _link.NOTE_LIMIT:
            raise BadCommand(f"a note is text of at most {_link.NOTE_LIMIT} characters")
        return MarkNote(mark=number, note=note, by=by)
    return {
        "stop": _link.Stop,
        "pause": _link.Pause,
        "resume": _link.Resume,
        "cancel": _link.CancelScheduledStop,
        "reward": _link.ManualReward,
    }[kind](by=by)


def not_delivered(why: str) -> tuple[int, dict]:
    """The answer for a command or a mark that did not reach the rig (spec §5.3)."""
    said = why if why.startswith("not delivered") else f"not delivered: {why}"
    return 504, {"status": "not_delivered", "said": said}


@dataclass
class _Job:
    """One piece of work for an `Outbox`'s thread, and the answer it leaves."""

    work: Callable[[object], tuple[int, dict]]
    answer: tuple[int, dict] | None = None
    done: threading.Event = field(default_factory=threading.Event)


class Outbox:
    """A bounded queue and the one thread that owns a sender (spec §2: each ZMQ socket
    has one owning thread). `wlx serve` has two: the command thread, whose sender is a
    `link.ZmqCommands`, and the mark thread, whose sender is a `link.ZmqMarks`.

    **The sender is built on the thread**, by `build`, and closed there, so no other
    thread ever touches its socket. `submit` puts one job on the queue -- or answers
    *busy* at once when the queue is full (spec §5.3) -- and waits for its answer.
    **Every job is answered**: by its work; by `not_delivered` when the work raised,
    or the sender could not be built; or, when the thread stops, by *not delivered:
    wlx serve is closing* -- so no HTTP handler waits forever. `stop` is the
    `Server`'s own stop event, so whatever stops the server stops this thread.
    """

    def __init__(
        self,
        name: str,
        build: Callable[[], object],
        depth: int,
        stop: threading.Event,
        *,
        busy: tuple[int, dict] = BUSY,
    ) -> None:
        self._build = build
        self._queue: queue.Queue = queue.Queue(maxsize=depth)
        self._stop = stop
        #: What a job is answered when the queue is full: `BUSY`, or the gaze thread's own.
        self._busy = busy
        self.thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def submit(self, work: Callable[[object], tuple[int, dict]]) -> tuple[int, dict]:
        return self.wait(self.post(work))

    def post(self, work: Callable[[object], tuple[int, dict]]) -> _Job:
        """**Queue `work`, never waiting**: the job, already answered *busy* when the queue
        is full or *not delivered* when the server is closing. `submit` is `post` then
        `wait`; the gaze thread's caller posts under its steering lock, so jobs run in the
        order their reports were numbered, and waits after letting it go (`Steering`)."""
        job = _Job(work)
        if self._stop.is_set():
            job.answer = not_delivered("wlx serve is closing")
            job.done.set()
            return job
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            job.answer = self._busy
            job.done.set()
        return job

    def wait(self, job: _Job) -> tuple[int, dict]:
        """`job`'s answer, once its work is done (`post`)."""
        while not job.done.wait(OUTBOX_POLL_S):
            if not self.thread.is_alive():
                # Fix round 1, Important 4: the thread may have answered this very
                # job and then exited between `wait` timing out and this check --
                # `job.done.set()` always happens before the thread's `_run`
                # returns (`_answer` sets it; the `finally` drain sets it for
                # anything still queued), so if it is set now, trust the job's own
                # answer over "closing." Only a job queued *after* the thread had
                # already left -- one the drain never saw either -- is answered
                # here.
                if job.done.is_set():
                    break
                return not_delivered("wlx serve is closing")
        return job.answer

    def _run(self) -> None:
        sender, broken = None, None
        try:
            sender = self._build()
        except Exception as exc:  # noqa: BLE001 -- said to every job, never hidden
            broken = _link._describe(exc)
        try:
            while not self._stop.is_set():
                try:
                    job = self._queue.get(timeout=OUTBOX_POLL_S)
                except queue.Empty:
                    continue
                self._answer(job, sender, broken)
        finally:
            if sender is not None:
                sender.close()
            while True:
                try:
                    job = self._queue.get_nowait()
                except queue.Empty:
                    break
                job.answer = not_delivered("wlx serve is closing")
                job.done.set()

    def _answer(self, job: _Job, sender: object, broken: str | None) -> None:
        try:
            job.answer = (
                not_delivered(f"wlx serve could not reach the rig ({broken})")
                if broken is not None
                else job.work(sender)
            )
        except Exception as exc:  # noqa: BLE001 -- answered, never hidden
            job.answer = not_delivered(_link._describe(exc))
        finally:
            job.done.set()


def _delivered(command, said: str = SENT) -> Callable[[object], tuple[int, dict]]:
    """The command thread's work for one command: deliver it and say so, in `said`, or
    say why not (spec §5.3)."""

    def work(commands) -> tuple[int, dict]:
        try:
            commands.deliver(command)
        except _link.NotDelivered as exc:
            return not_delivered(str(exc))
        return 200, {"status": "sent", "said": said}

    return work


def _rewarded(command: _link.ManualReward) -> Callable[[object], tuple[int, dict]]:
    """The command thread's work for a manual reward (PI, 2026-09-28): delivered
    **once**, like every command -- nothing on this path re-sends one, and a reward
    must never be the first thing that does -- and answered without guessing. *Sent*
    when the rig acknowledged it; *unknown* when it was handed over and not
    acknowledged (`link.Unacknowledged`), or failed in a way that cannot say whether
    it went, since it may already have been given; *not delivered* only when it never
    left, saying no reward was given."""

    def work(commands) -> tuple[int, dict]:
        try:
            commands.deliver(command)
        except _link.Unacknowledged:
            return REWARD_UNKNOWN
        except _link.NotDelivered as exc:
            return not_delivered(f"{exc}; no reward was given")
        except Exception:  # noqa: BLE001 -- a reward that may have gone is unknown
            return REWARD_UNKNOWN
        return 200, {"status": "sent", "said": REWARD_SENT}

    return work


# --- a demo's pointer (demo mode §3.8, §4.5) -------------------------------------------

#: **How long a page that steers a demo keeps the steer with nothing sent**, in seconds (§4.5):
#: past `pointer.LIVE_S` (0.5 s), so a page's stall that the rig reads as tracker loss keeps the
#: steer, and within a person's patience when a page closed without letting go. The demo plan's
#: call, claiming nothing about a rig.
STEER_HOLD_S = 1.0
#: How many pointer reports may wait for the gaze thread before `POST /gaze` answers *busy*:
#: one page steers, with one report in flight at a time (the page's own rule), so a few hold
#: every report a hand makes. Housekeeping, as `MARK_QUEUE_DEPTH`.
GAZE_QUEUE_DEPTH = 8
#: The longest page id a report may carry: a page's random id is a few dozen characters (a
#: UUID's 36). Housekeeping.
PAGE_ID_LIMIT = 64
#: How many pages' last forwarded sequence numbers are kept, so a report older than its page's
#: last is dropped (`Steering`): as many pages as may stream at once (`MAX_EVENT_STREAMS`). A page
#: forgotten past it has not steered since that many others did, and its next report is taken as
#: its newest. Housekeeping.
PAGES_REMEMBERED = MAX_EVENT_STREAMS
#: The count `wlx serve` numbers the reports it forwards with is a report's 32-bit `seq`
#: (`pointer.MESSAGE`), and goes round past its top. The rig keeps the highest it has while one
#: is current (`pointer.Source`), so the wrap costs one `pointer.LIVE_S` of tracker loss, once in
#: four billion reports.
_FORWARDED_MASK = 0xFFFFFFFF

#: What a page is told when its report was handed to the demo's gaze socket (§4.5): ZeroMQ queued
#: it to the connected demo service (`link.ZmqGaze.send`), whose newest report is the eye's at its
#: next frame. Whether a frame read it is not known here.
GAZE_SENT = (
    "sent: handed to the demo's gaze socket; the newest report there is the demo's eye at its "
    "next frame"
)
#: What the page is told when another page steers (§4.5), which it shows.
STEERED_ELSEWHERE = (
    409,
    {
        "status": "steered_elsewhere",
        "said": (
            f"steered from another page: this page may steer once that page lets go (Escape, "
            f"or closing it), or sends nothing for {STEER_HOLD_S:g} s"
        ),
    },
)
#: What a report is told while no demo session runs (§4.5): the latest frame is no demo's.
NOT_A_DEMO = (
    409,
    {
        "status": "not_a_demo",
        "said": "not a demo: no demo session is running here, so there is no eye to steer",
    },
)
#: A report not forwarded, and needing nothing done: older than its page's last, or off the
#: drawing from a page that does not steer.
DROPPED = (
    200,
    {
        "status": "dropped",
        "said": "not sent: a newer report from this page was sent already; the newest wins",
    },
)
UNSTEERED = (
    200,
    {
        "status": "dropped",
        "said": (
            "not sent: no page steers the demo, and this page takes the steer when its pointer "
            "is over the drawing"
        ),
    },
)
RELEASED = (200, {"status": "released", "said": "released: another page may steer the demo now"})
NOT_STEERING = (200, {"status": "released", "said": "released: this page was not steering"})
#: What the page is told when the gaze thread is full (`GAZE_QUEUE_DEPTH`).
GAZE_BUSY = (
    503,
    {
        "status": "busy",
        "said": (
            "busy: wlx serve is still sending earlier pointer reports, so this one was not sent; "
            "the next is sent in its place"
        ),
    },
)
#: Why a report was not sent: the rig's gaze socket took none, because no demo service is
#: connected. **Not between runs or paused** since the whole-build review's M1: both ends keep only
#: the newest report waiting (`link.ZmqGaze`), so a connected rig's socket never refuses one.
GAZE_NOT_TAKEN = (
    "the demo is not taking pointer reports now: its service is not connected, or is gone; the "
    "next report is sent in its place"
)
#: Why a report is not sent from a console with no gaze endpoint.
NO_GAZE_ENDPOINT = (
    "this console was started without the demo's gaze endpoint: give wlx serve "
    "--link PUB,REP,MARK,GAZE, as wlx taskd prints it"
)

#: A report's fields (§3.8), as the page sends them, and a release's.
_REPORT_FIELDS = frozenset({"page", "seq", "x", "y", "over", "b", "button", "held", "presses"})
_RELEASE_FIELDS = frozenset({"page", "release"})


class BadGaze(ValueError):
    """A `POST /gaze` body that is not a pointer report or a release. The message is the
    sentence the page is answered; nothing was sent."""


@dataclass(frozen=True, slots=True)
class GazeReport:
    """**One pointer report from a demo's page** (§3.8, §4.5): its page's random id, its `seq`
    rising with each the page sends, the pointer's x and y in degrees (+y up), whether it is over
    the drawing, B held, the mouse button down, the number keys held (bit `k - 1` for key `k`),
    and each of the `pointer.KEYS` keys' running press count."""

    page: str
    seq: int
    x: float
    y: float
    over: bool
    b: bool
    button: bool
    held: int
    presses: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class GazeRelease:
    """A page letting go of the steer (§4.5): Escape, or the page closed."""

    page: str


def _whole(value: object, top: int) -> bool:
    """Whether `value` is a whole number from 0 to `top`, a `bool` not being one."""
    return not isinstance(value, bool) and isinstance(value, int) and 0 <= value <= top


def parse_gaze(data: object) -> GazeReport | GazeRelease:
    """One `POST /gaze` body (§4.5): `{"page", "seq", "x", "y", "over", "b", "button", "held",
    "presses"}`, or `{"page", "release": true}`. **Checked whole before anything is sent**: a
    field missing or extra, or of the wrong kind, is refused with a sentence (`BadGaze`). `seq`
    and each press count are whole numbers a browser's JSON carries exactly (`MARK_ID_LIMIT`,
    `Number.MAX_SAFE_INTEGER`); the counts are sent modulo 65536, as the rig reads them
    (`pointer.pack`). x and y are finite: the rig drops a report that is not (`pointer.Source`),
    and this answers it instead."""
    if not isinstance(data, dict):
        raise BadGaze("a pointer report is one JSON object")
    page = data.get("page")
    if (
        not isinstance(page, str)
        or not 1 <= len(page) <= PAGE_ID_LIMIT
        or not page.isascii()
        or not page.isprintable()
    ):
        raise BadGaze(
            f"a pointer report names its page: an id of 1 to {PAGE_ID_LIMIT} printable ASCII "
            f"characters"
        )
    if "release" in data:
        if set(data) != _RELEASE_FIELDS or data["release"] is not True:
            raise BadGaze("a release is the page's id and release: true, and nothing else")
        return GazeRelease(page)
    missing, extra = _REPORT_FIELDS - set(data), set(data) - _REPORT_FIELDS
    if missing or extra:
        said = [f"lacks {', '.join(sorted(missing))}"] if missing else []
        said += [f"takes no {', '.join(sorted(extra))}"] if extra else []
        raise BadGaze(f"a pointer report {' and '.join(said)}")
    if not _whole(data["seq"], MARK_ID_LIMIT):
        raise BadGaze(
            f"a report's seq is a whole number from 0 to {MARK_ID_LIMIT}, rising with each "
            f"report its page sends"
        )
    for axis in ("x", "y"):
        value = data[axis]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not _finite(value):
            raise BadGaze(
                f"a report's {axis} is the pointer's position in degrees, a finite number"
            )
    for flag in ("over", "b", "button"):
        if not isinstance(data[flag], bool):
            raise BadGaze(f"a report's {flag} is true or false")
    keys = _pointer.KEYS
    if not _whole(data["held"], 2**keys - 1):
        raise BadGaze(
            f"a report's held is the number keys held, bit k - 1 for key k, from 0 to "
            f"{2**keys - 1}"
        )
    presses = data["presses"]
    if (
        not isinstance(presses, list)
        or len(presses) != keys
        or not all(_whole(count, MARK_ID_LIMIT) for count in presses)
    ):
        raise BadGaze(
            f"a report's presses are the {keys} number keys' press counts, each a whole number "
            f"from 0 to {MARK_ID_LIMIT}"
        )
    return GazeReport(
        page=page, seq=data["seq"], x=float(data["x"]), y=float(data["y"]),
        over=data["over"], b=data["b"], button=data["button"], held=data["held"],
        presses=tuple(presses),
    )


def _pushed(message: bytes) -> Callable[[object], tuple[int, dict]]:
    """The gaze thread's work for one packed report: hand it to the demo's gaze socket without
    waiting (`link.ZmqGaze.send`) and say whether it went."""

    def work(gaze) -> tuple[int, dict]:
        if gaze.send(message):
            return 200, {"status": "sent", "said": GAZE_SENT}
        return not_delivered(GAZE_NOT_TAKEN)

    return work


class Steering:
    """**Who steers a demo's eye** (§4.5), and the count the rig reads reports by.

    **One page steers at a time**: the first whose report says its pointer is over the drawing
    takes the steer, and keeps it, off the drawing included, until it lets go (`release`) or
    sends nothing for `STEER_HOLD_S` on `clock`. Another page's report meanwhile is answered
    409 (`STEERED_ELSEWHERE`); one off the drawing while no page steers is not sent
    (`UNSTEERED`). **A report not newer than the last forwarded from its page is dropped**
    (`DROPPED`), its page's `seq` being the page's own count.

    **The rig reads reports by `wlx serve`'s own count**, `forwarded`, rising with each report
    sent whichever page steers (the demo plan's call: the rig keeps the highest, `pointer.Source`),
    so a page that takes the steer is never taken for an older one. A report is numbered, packed
    (`pointer.pack`) and queued on the gaze thread under one lock, so the thread sends them in the
    order numbered; the answer is waited for after the lock is let go. `wlx serve` restarted
    counts from 1 again, and the rig, keeping its highest while one is current, takes its reports
    once `pointer.LIVE_S` has passed.
    """

    def __init__(self, outbox: Outbox, *, clock: Callable[[], float] = _welfare.steady_seconds):
        self._outbox = outbox
        self._clock = clock
        self._lock = threading.Lock()
        #: The page that steers, and when it was last heard from, on `clock`.
        self._page: str | None = None
        self._heard = 0.0
        #: Each page's last forwarded `seq`, the newest `PAGES_REMEMBERED` pages.
        self._seqs: OrderedDict[str, int] = OrderedDict()
        #: The last number a forwarded report was sent with.
        self._forwarded = 0

    def report(self, report: GazeReport) -> tuple[int, dict]:
        """Forward `report` if its page steers, or takes the steer, and it is its page's newest;
        else say why not."""
        now = self._clock()
        with self._lock:
            if self._page is not None and now - self._heard >= STEER_HOLD_S:
                self._page = None  # quiet for the hold: the steer is free
            if self._page is not None and self._page != report.page:
                return STEERED_ELSEWHERE
            if self._page is None and not report.over:
                return UNSTEERED
            if self._page == report.page:
                self._heard = now
            last = self._seqs.get(report.page)
            if last is not None and report.seq <= last:
                return DROPPED
            self._page, self._heard = report.page, now
            self._seqs[report.page] = report.seq
            self._seqs.move_to_end(report.page)
            while len(self._seqs) > PAGES_REMEMBERED:
                self._seqs.popitem(last=False)
            self._forwarded = (self._forwarded + 1) & _FORWARDED_MASK
            message = _pointer.pack(
                self._forwarded, report.x, report.y, over=report.over, b=report.b,
                button=report.button, held=report.held, presses=report.presses,
            )
            job = self._outbox.post(_pushed(message))
        return self._outbox.wait(job)

    def release(self, page: str) -> tuple[int, dict]:
        """`page` lets go of the steer, if it holds it."""
        with self._lock:
            if self._page != page:
                return NOT_STEERING
            self._page = None
        return RELEASED


@dataclass(frozen=True)
class Remote:
    """The https page's sign-in (b2b spec §3-§5): this rig's page entry, and the checker
    every command from the network goes through."""

    page: "_signin.RigPage"
    checker: "_signin.Checker"


def _no_passphrase() -> str:
    raise ssl.SSLError("the key has a passphrase")  # never prompt on the terminal


def tls_context(cert: Path, key: Path) -> ssl.SSLContext:
    """The https listener's TLS, server side, TLS 1.2 at least (spec §3). Raises
    `SystemExit` with a sentence that names the flags and never the key's contents or path."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(certfile=cert, keyfile=key, password=_no_passphrase)
    except (OSError, ssl.SSLError) as exc:
        raise SystemExit(
            f"refused: --tls-cert and --tls-key could not be loaded as a certificate chain "
            f"and its private key, which must have no passphrase ({type(exc).__name__})"
        ) from None
    return context


class _PageServer(ThreadingHTTPServer):
    """The https listener (spec §3). **The TLS handshake runs on the connection's own
    thread** (`finish_request`), never on the thread that accepts, so one slow or stalled
    client cannot stop others connecting."""

    def __init__(self, address, handler, context: ssl.SSLContext) -> None:
        self._context = context
        super().__init__(address, handler)

    def finish_request(self, request, client_address) -> None:
        request.settimeout(REQUEST_TIMEOUT_S)
        try:
            tls = self._context.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            return  # a failed handshake asked nothing, so there is nothing to answer
        try:
            self.RequestHandlerClass(tls, client_address, self)
        except (ssl.SSLError, ConnectionError):
            pass  # a junk record or a reset after the handshake: the client left, say nothing
        finally:
            tls.close()


def make_handler(
    hub: Hub,
    *,
    token: str,
    stale_after_s: float,
    keepalive_s: float = KEEPALIVE_S,
    hosts: frozenset[str] = LOOPBACK_NAMES,
    dispatch: Callable[[object], tuple[int, dict]] | None = None,
    remote: Remote | None = None,
    https_page: bool = False,
    https_off: str | None = None,
    max_streams: int = MAX_EVENT_STREAMS,
    steer: Callable[[object], tuple[int, dict]] | None = None,
) -> type[BaseHTTPRequestHandler]:
    """A handler class closing over `hub` and the token, built the way wl-preproc's
    `make_handler` is and for its reason: `BaseHTTPRequestHandler` handles the whole
    request inside `__init__`, so all it needs must already be class attributes.

    Refuses an empty or non-ASCII token before building anything: `hmac.compare_digest`
    cannot compare a non-ASCII `str`, and a handler built from one would refuse every
    request, the correct one included (wl-preproc, review round 2's Minor 7).

    **P4d-2b b2a.** `hosts` is every name a request's `Host` may give (`box_names`);
    anything else is a JSON 421. `dispatch` sends a parsed command and says what
    became of it (`Server.dispatch`); a handler given none answers every command
    *not delivered*. `https_off` is why the rig's https page is off, shown on the box's own
    page (b2b-ready §3.1).

    **Demo mode §4.5.** `steer` takes each `POST /gaze` body past the write checks and
    `parse_gaze`, and says what became of it (`Server.steer`); a handler given none answers every
    report *not delivered*.
    """
    if not token or not token.isascii():
        raise ValueError(
            "the /health bearer token must be non-empty ASCII: hmac.compare_digest "
            "cannot compare anything else, and a handler built from one would refuse "
            "every request, the correct one included"
        )

    class ConsoleHandler(BaseHTTPRequestHandler):
        _hub = hub
        _token = token
        _stale_after_s = stale_after_s
        _keepalive_s = keepalive_s
        _hosts = hosts
        _remote = remote
        #: Whether a rig's plain-http page has an https page beside it (b2b spec §3).
        _https_page = https_page
        #: Why the rig's https page is off, for the box's own page (b2b-ready §3.1).
        _https_off = https_off
        #: The most `/events` streams the hub may hold (`MAX_EVENT_STREAMS`, XC-043).
        _max_streams = max_streams
        # A function stored on a class becomes a method; `staticmethod` keeps it the
        # plain callable it was given.
        _dispatch = None if dispatch is None else staticmethod(dispatch)
        _steer = None if steer is None else staticmethod(steer)
        # No interpreter version in any `Server` header (wl-preproc's Important 5).
        server_version = ""
        sys_version = ""
        timeout = REQUEST_TIMEOUT_S

        def _authorized(self) -> bool:
            """`Authorization: Bearer <token>`, the scheme matched case-insensitively
            (RFC 7235 §2.1), the token by `hmac.compare_digest` on UTF-8 bytes --
            wl-preproc's `_authorized`. Missing, malformed and wrong take one path."""
            value = self.headers.get("Authorization")
            if value is None:
                return False
            scheme, _, candidate = value.partition(" ")
            if scheme.lower() != "bearer" or not candidate:
                return False
            return hmac.compare_digest(
                candidate.encode("utf-8"), self._token.encode("utf-8")
            )

        def _security_headers(self, *, cache: str) -> None:
            """The three headers every response carries, `/events` included -- written
            here once so a header added later cannot land in `_write`'s responses
            and stay missing from the streamed one (F3)."""
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")

        #: Whether this request has begun its answer, which a 500 after that cannot replace.
        _answered = False

        def send_response(self, code, message=None) -> None:
            self._answered = True
            super().send_response(code, message)

        def _path(self) -> str:
            """The request's path without its query string (b2b spec §3): the page's
            return from wl.works carries an authorization code in it."""
            # A request line too malformed to parse has no `path` yet, and is still logged.
            return getattr(self, "path", "-").partition("?")[0]

        def log_request(self, code="-", size="-") -> None:
            """The stdlib's request line without its query string (the plan's Ruling 10):
            the page's return from wl.works carries an authorization code there."""
            self.log_message('"%s %s" %s', self.command, self._path(), str(code))

        def _refuse_after_reading(self, status: int, payload: dict) -> None:
            """Answer a refusal after reading the request's body, on either listener, so
            closing the connection on unread bytes does not reset the answer away (the
            client would see a reset, never the sentence: XC-120). Reads and discards at
            most `REFUSAL_DRAIN_LIMIT` bytes and for at most `REFUSAL_DRAIN_S` seconds.

            **The refusal is always sent**: a client that stalls, drips, or leaves
            mid-body costs its own thread that long and is then answered with the
            refusal it was owed (never a 500), the connection closed. A body declared
            longer than the limit, and a body with no `Content-Length` (chunked), cannot
            be read to its end: the answer carries `Connection: close`, which tells the
            client the connection ends. **A client that keeps sending past the close may
            still see a reset in place of the answer**; the page never does."""
            length = self.headers.get("Content-Length") or ""
            close = False
            if length.isascii() and length.isdecimal():
                wanted = int(length)
                close = wanted > REFUSAL_DRAIN_LIMIT
                try:
                    self._drain(min(wanted, REFUSAL_DRAIN_LIMIT))
                except OSError:  # `TimeoutError` too: the client stalled, dripped or left
                    close = True
            elif self.headers.get("Transfer-Encoding") is not None:
                close = True  # chunks nobody will read must not become the next request
            headers: tuple = ()
            if close:
                self.close_connection = True
                headers = (("Connection", "close"),)
            try:
                self.connection.settimeout(self.timeout)
            except OSError:
                pass
            self._write(status, json.dumps(payload).encode("utf-8"), "application/json", headers)

        def _drain(self, count: int) -> None:
            """Read and drop `count` bytes within `REFUSAL_DRAIN_S`: raises `TimeoutError`
            when that passes first and `ConnectionError` if the client closes first."""
            end = time.monotonic() + REFUSAL_DRAIN_S
            while count > 0:
                left = end - time.monotonic()
                if left <= 0:
                    raise TimeoutError("the refused request's body did not arrive in time")
                self.connection.settimeout(left)
                chunk = self.rfile.read1(min(count, 8192))
                if not chunk:
                    raise ConnectionError("the client closed before its body was complete")
                count -= len(chunk)

        def _write(
            self,
            status: int,
            body: bytes,
            content_type: str,
            headers: tuple = (),
            cache: str = "no-store",
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._security_headers(cache=cache)
            if status == 401:
                # RFC 9110 §15.5.2: a 401 names the scheme. Both tokens here are bearer
                # tokens: `/health`'s, and a member's sign-in on the https page.
                self.send_header("WWW-Authenticate", "Bearer")
            elif status == 405:
                # RFC 9110 §15.5.6: a 405 names the methods the path does answer. `HEAD`
                # is refused (`do_HEAD`), so it is not among them.
                self.send_header("Allow", "POST" if self._path() in _WRITES else "GET")
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":  # RFC 9110 §9.3.2: a HEAD response has no body
                self.wfile.write(body)

        def _send_json(self, status: int, payload: dict) -> None:
            self._write(status, json.dumps(payload).encode("utf-8"), "application/json")

        def _host_ok(self) -> bool:
            """Whether this request's `Host` names this console (spec §2, §5.3). On the
            https page that is this rig's own page host, exactly, and nothing else."""
            return self._names_this_console(self.headers.get("Host"))

        def _names_this_console(self, given: str | None) -> bool:
            if self._remote is not None:
                return (given or "").strip().lower() == self._remote.page.host
            return host_name(given) in self._hosts

        def may_write(self) -> bool:
            """Spec §2's first two checks -- a loopback peer, and a `Host` naming
            loopback -- which are what a page's controls are greyed by. `POST
            /commands` adds the other two, `Origin` and `Content-Type`. **Never on
            the https page** (b2b spec §3): the box's checks do not apply there."""
            if self._remote is not None:
                return False
            return on_box(self.client_address[0]) and names_loopback(
                host_name(self.headers.get("Host"))
            )

        def _from_the_box(self) -> bool:
            """All four of spec §2's checks on a write: a loopback peer; `Host` naming
            loopback (against DNS rebinding); `Origin` being the page this console
            serves on that host (against a cross-site post from another page open
            in the box's browser); and `Content-Type: application/json`, which makes
            a browser ask a preflight this server never approves."""
            host = self.headers.get("Host") or ""
            origin = self.headers.get("Origin") or ""
            content = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            return (
                self.may_write()
                and origin.lower() == f"http://{host}".lower()
                and content.lower() == "application/json"
            )

        def send_error(self, code, message=None, explain=None) -> None:
            """Every error the stdlib raises on its own, as JSON and never its HTML
            page (wl-preproc's `send_error`, read 2026-09-26). `message` and `explain`
            are discarded: the stdlib formats the caller's own bytes into them.

            **An unknown method is 405 on a known path and 404 elsewhere**, where
            wl-preproc answers 401: every one of its paths needs the token, and here
            only `GET /health` does -- the pages are open to the LAN (spec §2).

            **A foreign `Host` still answers 421 here too** (fix round 1, security
            review Important 3): an unknown method never reaches `do_GET`/`do_POST`,
            so it bypassed their own `Host` check entirely -- `BREW /` with `Host:
            evil.example` used to answer 405. A request with no `Host` at all keeps
            its existing 405/404 unchanged (`test_a_method_the_stdlib_does_not_know_
            gets_json_not_its_html_page`'s own pin: an HTTP/1.0 client that sends
            none).
            """
            if code == 501:
                given = self.headers.get("Host") if self.headers else None
                if given is not None and not self._names_this_console(given):
                    self._send_json(421, _MISDIRECTED)
                    return
                code = 405 if getattr(self, "path", None) in _ROUTES else 404
            self._send_json(code, _ERRORS.get(code, _FALLBACK))

        def _refuse_method(self) -> None:
            if not self._host_ok():
                self._send_json(421, _MISDIRECTED)
                return
            code = 405 if self.path in _ROUTES else 404
            self._send_json(code, _ERRORS[code])

        # Every verb a client commonly sends besides GET and POST. An `OPTIONS`
        # preflight is one of them: refused, so a cross-site page is never let to
        # post JSON (spec §2's fourth check).
        do_PUT = _refuse_method
        do_DELETE = _refuse_method
        do_PATCH = _refuse_method
        do_OPTIONS = _refuse_method
        do_HEAD = _refuse_method
        do_TRACE = _refuse_method

        def do_POST(self) -> None:
            # A refusal reads the request's body first, so the client reads the answer
            # and not a reset (`_refuse_after_reading`, XC-120).
            refuse = self._refuse_after_reading
            if not self._host_ok():
                refuse(421, _MISDIRECTED)
                return
            if self.path == "/commands":
                self._command()
            elif self.path == "/gaze":
                self._gaze()
            elif self._remote is not None and self.path in ("/whoami", "/signout"):
                self._account(self.path)
            else:
                code = 405 if self.path in _ROUTES else 404
                refuse(code, _ERRORS[code])

        def _from_the_page(self) -> bool:
            """The https page's write checks before the token's (b2b spec §3): `Origin` is
            exactly the page's origin, and `Content-Type: application/json`."""
            origin = (self.headers.get("Origin") or "").strip().lower()
            content = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            return origin == self._remote.page.origin and content == "application/json"

        def _signed_in(self):
            """The `signin.Accepted` this request's token names, or `None` after answering
            its 401 (the body read first, so the client can read the answer). The token
            is never written to the answer or the log."""
            from wl_xcon import signin  # loaded already: a `Remote` exists

            try:
                return self._remote.checker.check(self.headers.get("Authorization"))
            except signin.Refused as refused:
                self._refuse_after_reading(
                    401, {"status": "refused", "reason": refused.reason, "said": refused.said}
                )
                return None

        def _discard_body(self) -> bool:
            """Read and drop a request's body of at most `BODY_LIMIT` bytes, so a keep-alive
            connection stays in step. `False` after answering a body it would not take."""
            length = self.headers.get("Content-Length") or ""
            if not length.isascii() or not length.isdecimal():
                self._refuse_after_reading(
                    400, {"status": "refused", "said": "a request needs a Content-Length"}
                )
                return False
            if int(length) > BODY_LIMIT:
                self._refuse_after_reading(
                    413, {"status": "refused", "said": f"a request is at most {BODY_LIMIT} bytes"}
                )
                return False
            self.rfile.read(int(length))
            return True

        def _account(self, path: str) -> None:
            """`POST /whoami` and `POST /signout` on the https page (b2b spec §4)."""
            if not self._from_the_page():
                self._refuse_after_reading(403, {"status": "refused", "said": FROM_THE_PAGE})
                return
            if path == "/signout":
                if self._discard_body():
                    self._remote.checker.sign_out(self.headers.get("Authorization"))
                    self._send_json(200, {"status": "signed_out", "said": SIGNED_OUT_HERE})
                return
            accepted = self._signed_in()
            if accepted is None or not self._discard_body():
                return
            self._send_json(
                200,
                {
                    "status": "signed_in",
                    "name": accepted.member.name,
                    "shown": str(accepted.member),
                    "expires_at": accepted.expires_at,
                },
            )

        def _writer(self):
            """**The write checks**, factored out of `_command` so that `POST /commands` and
            `POST /gaze` take them alike (demo mode §4.5, §14 item 13): `/gaze` is gated
            exactly as `/commands` is, never by `may_write` alone, which is false on the https
            page. Returns who may write -- the member a token names on the https page, `None`
            on the box's -- or `_REFUSED` once the refusal is answered, its body read first
            (`_refuse_after_reading`).

            **A token never reaches the box's checks** (b2b spec §3): on the plain-http
            listener a request carrying `Authorization` is refused first of all, then spec
            §2's four checks (`_from_the_box`). On the https listener the write is the
            signed-in member's: the page's `Origin` and `Content-Type`, then the token."""
            refuse = self._refuse_after_reading
            if self._remote is None and self.headers.get("Authorization") is not None:
                refuse(403, {"status": "refused", "said": TOKEN_OVER_HTTP})
                return _REFUSED
            if self._remote is not None:
                if not self._from_the_page():
                    refuse(403, {"status": "refused", "said": FROM_THE_PAGE})
                    return _REFUSED
                accepted = self._signed_in()
                return _REFUSED if accepted is None else accepted.member
            if not self._from_the_box():
                said = _web.CONTROLS_ELSEWHERE if self._https_page else _web.CONTROLS_AT_THE_BOX
                refuse(403, {"status": "refused", "said": said})
                return _REFUSED
            return None

        def _length(self, what: str) -> int | None:
            """The body's declared length, at most `BODY_LIMIT`, or `None` once a body with
            none, or a longer one, is refused unread (`_refuse_after_reading`). `what` names
            it in the sentence: "a command", "a pointer report"."""
            length = self.headers.get("Content-Length") or ""
            if not length.isascii() or not length.isdecimal():
                self._refuse_after_reading(
                    400, {"status": "refused", "said": f"{what} needs a Content-Length"}
                )
                return None
            if int(length) > BODY_LIMIT:
                self._refuse_after_reading(
                    413, {"status": "refused", "said": f"{what} is at most {BODY_LIMIT} bytes"}
                )
                return None
            return int(length)

        def _command(self) -> None:
            """`POST /commands` (spec §5.3): one JSON command, checked and validated before
            anything is queued, then sent and answered *sent*, *not delivered* or *busy*.

            The write checks are `_writer`'s; on the https listener the body takes no `by`,
            the command being the signed-in member's. Every refusal before the body is read
            reads it first (`_refuse_after_reading`)."""
            member = self._writer()
            if member is _REFUSED:
                return
            length = self._length("a command")
            if length is None:
                return
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                request = parse_command(data, actor=member)
            except (UnicodeDecodeError, ValueError) as exc:
                # `BadCommand` is a `ValueError`, and so is `json`'s own error.
                said = str(exc) if isinstance(exc, BadCommand) else "a command is one JSON object"
                self._send_json(400, {"status": "refused", "said": f"not sent: {said}"})
                return
            except Exception:  # noqa: BLE001 -- a last resort, answered, never a dead thread
                # Fix round 1, Important 2: a body shape this file has not
                # anticipated must still get an answer, not kill the handler
                # thread the way an unhashable `kind` and an oversized integer
                # both used to before their own guards existed. Never the
                # exception's own text: a body malformed enough to reach here is
                # not proven safe to echo back.
                self._send_json(
                    400,
                    {
                        "status": "refused",
                        "said": "not sent: this request could not be read as a command",
                    },
                )
                return
            if self._dispatch is None:
                code, answer = not_delivered("this console has no command path")
            else:
                code, answer = self._dispatch(request)
            self._send_json(code, answer)

        def _gaze(self) -> None:
            """`POST /gaze` (demo mode §4.5): one pointer report, or a release, from a demo's
            page. **Gated exactly as `/commands` is** (`_writer`), then its length and its body
            checked (`parse_gaze`), each refusal a sentence; then `steer` (`Server.steer`) says
            what became of it: *sent*, *dropped*, *released*, 409 *not a demo* or *steered from
            another page*, *busy* or *not delivered*. Who steers is recorded nowhere: a demo's
            eye is no command."""
            if self._writer() is _REFUSED:
                return
            length = self._length("a pointer report")
            if length is None:
                return
            try:
                report = parse_gaze(json.loads(self.rfile.read(length).decode("utf-8")))
            except (UnicodeDecodeError, ValueError) as exc:
                # `BadGaze` is a `ValueError`, and so is `json`'s own error.
                said = (
                    str(exc) if isinstance(exc, BadGaze) else "a pointer report is one JSON object"
                )
                self._send_json(400, {"status": "refused", "said": f"not sent: {said}"})
                return
            except Exception:  # noqa: BLE001 -- answered, never a dead thread (`_command`'s)
                self._send_json(
                    400,
                    {
                        "status": "refused",
                        "said": "not sent: this request could not be read as a pointer report",
                    },
                )
                return
            if self._steer is None:
                code, answer = not_delivered("this console has no gaze path")
            else:
                code, answer = self._steer(report)
            self._send_json(code, answer)

        def do_GET(self) -> None:
            if not self._host_ok():
                self._send_json(421, _MISDIRECTED)
                return
            path = self._path()
            if path == "/":
                self._page()
            elif path == "/color-preview":
                # A new color's preview (the console settings build's Task 8): it writes nothing,
                # so any viewer may ask, and its fields are its query string.
                self._color_preview()
            elif "?" in self.path:
                self._refuse_method()  # only the page and a preview take a query string
            elif path == "/events":
                self._events()
            elif path == "/health":
                if not self._authorized():
                    self._send_json(401, _UNAUTHORIZED)
                    return
                self._health()
            elif path in _FONTS:
                self._font(_FONTS[path])
            else:
                # 405 for a known path that takes another method -- `/commands`,
                # since b2a -- and 404 for anything else.
                self._refuse_method()

        def _color_preview(self) -> None:
            """`color_preview` on the latest frame, its fields the query string's."""
            from urllib.parse import parse_qs, urlsplit

            latest, _ = self._hub.snapshot(on_box=on_box(self.client_address[0]),
                                           stale_after_s=self._stale_after_s)
            # **At most 16 fields** (TSK-75: a fixed number says its reason): any viewer may ask
            # for a preview, so the parse is bounded rather than left to the query's length; a
            # well-formed one names at most five -- `set`, `method` and a method's numbers, at most
            # three (`colordef.NUMBERS`, `OPTIONAL`, `FRAMING`). Why 16 rather than five was not
            # written down when the console settings build's Task 8 chose it: a margin above
            # five, the builder's.
            try:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True,
                                 max_num_fields=16)
            except ValueError:
                code, answer = 400, {"x": None, "y": None, "srgb": None, "in_srgb": None,
                                     "said": "a color preview takes at most 16 fields"}
            else:
                code, answer = color_preview(latest, query)
            self._send_json(code, answer)

        def _font(self, font) -> None:
            """A bundled font (PI, 2026-09-26: "bundle the fonts"). Cached a day: the
            files change only with the package."""
            self._write(
                200, _web.font_bytes(font), "font/woff2", cache="max-age=86400"
            )

        def _sign_in(self) -> "_web.SignIn | None":
            """What the https page needs to sign a member in, or `None` on the box's
            page. While the rig cannot check a sign-in, the page says why
            (`Checker.unavailable`: b2b-ready §3.4) and offers none."""
            if self._remote is None:
                return None
            checker = self._remote.checker
            unavailable = checker.unavailable
            discovery = None if unavailable is not None else checker.discovery
            page = self._remote.page
            return _web.SignIn(
                authorize=None if discovery is None else discovery.authorization_endpoint,
                token_endpoint=None if discovery is None else discovery.token_endpoint,
                client_id=page.client_id,
                page=page.page,
                resource=page.origin,
                unavailable=unavailable,
            )

        def _page(self) -> None:
            can_write = self.may_write()
            latest, view = self._hub.snapshot(
                on_box=on_box(self.client_address[0]),
                stale_after_s=self._stale_after_s,
                can_write=can_write,
                signin=self._remote is not None,
                https_page=self._https_page,
                streams_max=self._max_streams,
            )
            nonce = secrets.token_urlsafe(16)
            body = _web.page(
                _web.fragments(latest, view),
                stale_after_s=self._stale_after_s,
                nonce=nonce,
                can_write=can_write,
                signin=self._sign_in(),
                https_page=self._https_page,
                https_off=self._https_off,
                can_gaze=view.can_gaze,
            )
            connect = ""
            if self._remote is not None:
                discovery = self._remote.checker.discovery
                connect = "" if discovery is None else discovery.token_origin
            self._write(
                200,
                body.encode("utf-8"),
                "text/html; charset=utf-8",
                (("Content-Security-Policy", _csp(nonce, connect)),),
            )

        def _health(self) -> None:
            """`health.response` from one snapshot, the refusal included (Ruling 11,
            2026-09-27): a console refusing every frame is `degraded`, never `ok`."""
            latest, view = self._hub.snapshot(
                on_box=False, stale_after_s=self._stale_after_s, streams_max=self._max_streams
            )
            body = _health.response(
                latest,
                frame_age_s=view.frame_age_s,
                stale_after_s=view.stale_after_s,
                rejected=view.rejected,
                endpoint=view.endpoint,
                streams=view.streams,
            )
            self._send_json(200, body)

        def _events(self) -> None:
            """One browser's stream (spec §4.3): a full render on connect, then an
            event per frame it keeps up with, and a refresh each `keepalive_s`
            without one, until the hub closes or the browser goes away.

            **A quiet interval re-renders, it does not send a comment** (Ruling 12,
            2026-09-27). The page's panes age between frames -- the time since the
            last reward adds the seconds this process has held the frame, and
            *wl-works sees* turns `degraded` when the frame goes stale -- and a
            comment moved neither, so a stalled stream kept `ok · Last frame 0 s
            ago` on the page while `GET /health` said `degraded`. The refresh is
            `_send_frame` like any other event: only what changed, with `live` and
            `age`, and possibly no fragment at all.

            `take` is only ever used as a wake-up and to notice `CLOSED` -- never as
            the frame that gets rendered (F2, below `_send_frame`).

            **A demo's drawings go as their own events** (demo mode §4.4): after the full
            render on connect, the latest drawing if there is one; then after every wake-up
            the latest drawing if it is newer than the last this stream sent, so they arrive
            in order, the newest winning. A wake-up only a drawing made (`DRAWN`) sends no
            frame event."""
            box = on_box(self.client_address[0])
            can_write = self.may_write()
            try:
                subscriber = self._hub.subscribe(on_box=box, limit=self._max_streams)
            except StreamsFull:
                self._send_json(503, _STREAMS_FULL)
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self._security_headers(cache="no-store")
                self.end_headers()
                self.wfile.write(f"retry: {RETRY_MS}\n\n".encode("ascii"))
                sent: dict[str, str] = {}
                self._send_frame(box, can_write, sent)
                drawn = self._send_drawing(0)
                while True:
                    try:
                        item = self._hub.take(subscriber, timeout=self._keepalive_s)
                    except queue.Empty:
                        self._send_frame(box, can_write, sent)
                        continue
                    if item is CLOSED:
                        return
                    if item is not DRAWN:
                        self._send_frame(box, can_write, sent)
                    drawn = self._send_drawing(drawn)
            except OSError:
                # A broken pipe, a reset, or a write that timed out: the browser went
                # away. There is nobody to tell; `finally` forgets it.
                return
            finally:
                self._hub.unsubscribe(subscriber)

        def _send_frame(self, box: bool, can_write: bool, sent: dict) -> None:
            """One event: the fragments that differ from what this browser holds --
            all of them on connect -- whether more frames are due (`live`), which is
            when the page's stale timer runs, and `age`, the seconds this process
            has held the latest frame on its steady clock, `None` before any.

            **The page's stale timer runs from `age`** (Ruling 12, 2026-09-27): its
            baseline is the event's arrival less `age`, so a page that connects
            onto an old frame, or is woken by a refusal, never restarts the clock
            the way resetting it on arrival did.

            **Frame and view come from the same `snapshot()` call** (F2, security
            review fix round 1). `_events`'s `take` only wakes this up; rendering the
            frame `take` handed back beside a `view` read a moment later could pair
            an older frame with a newer frame's age, understating the time since the
            last reward by one inter-frame interval -- the direction that hides a
            working, unpaid animal. Telemetry is latest-wins, so reading both from
            one snapshot is always safe: whatever is newest when this runs is what
            is sent, never a stale value carried in from `take`.
            """
            latest, view = self._hub.snapshot(
                on_box=box,
                stale_after_s=self._stale_after_s,
                can_write=can_write,
                signin=self._remote is not None,
                https_page=self._https_page,
                streams_max=self._max_streams,
            )
            parts = _web.fragments(latest, view)
            changed = {key: html for key, html in parts.items() if sent.get(key) != html}
            sent.update(changed)
            self.wfile.write(
                event(
                    {
                        "frags": changed,
                        "live": _health.expects_frames(latest),
                        "age": view.frame_age_s,
                    }
                )
            )

        def _send_drawing(self, after: int) -> int:
            """The hub's latest drawing as its own event, `drawn`, its payload `{"svg": ...,
            "keys": ...}` -- `demoscreen.render`'s fragment, and the key list for that screen's
            keys (`web.demo_keys`; demo mode §4.3, Task 9), rendered here as every word of the
            page is -- if it is newer than drawing `after`, the last this stream sent; the
            number of the last sent."""
            number, svg, keys = self._hub.drawing_and_keys()
            if number <= after:
                return after
            self.wfile.write(event({"svg": svg, "keys": _web.demo_keys(keys)}, name="drawn"))
            return number

    def _backstop(handler):
        """`handler` with a last resort (XC-042): one that raises answers `500` with a fixed
        JSON body (`_ERRORS`) and the connection is closed, never the exception's text or a
        traceback to the client, and never a dead thread with no answer. What failed is logged
        where the server logs (`log_error`). A handler that had begun its answer (an event
        stream) cannot be given a second one: its connection is closed. **Only the `do_*` verbs
        are covered:** a verb the standard library does not know goes to `send_error` (501)
        instead, which answers JSON already and holds no handler of ours."""

        @functools.wraps(handler)
        def guarded(self) -> None:
            self._answered = False
            try:
                handler(self)
            except (ConnectionError, ssl.SSLError):
                # A client that left mid-request: no fault of the server's, nobody to answer.
                # Left to what handled it before the backstop -- `_PageServer.finish_request`
                # drops it silently, the standard library's `handle_error` reports it.
                raise
            except Exception as exc:  # noqa: BLE001 -- answered and logged, never hidden
                self.log_error(
                    "%s %s raised %s: %s", self.command, self._path(), type(exc).__name__,
                    traceback.format_exc().replace("\n", " | "),
                )
                self.close_connection = True
                if not self._answered:
                    try:
                        self._send_json(500, _ERRORS[500])
                    except OSError:
                        pass  # the client is gone; the log line above is all there is

        return guarded

    # **Every** `do_*`, by name, so a verb added later goes through the backstop with no
    # further change: GET, POST and the refused verbs alike.
    for _name in [name for name in vars(ConsoleHandler) if name.startswith("do_")]:
        setattr(ConsoleHandler, _name, _backstop(getattr(ConsoleHandler, _name)))

    return ConsoleHandler


#: How long the telemetry thread's receive waits before it looks again at whether to
#: stop, so `Server.close` returns promptly. A responsiveness choice, not a
#: measurement; `wlx console` keeps `ZmqConsole`'s 5 s.
RECEIVE_TIMEOUT_S = 0.5


class Server:
    """`wlx serve`'s whole process, as an object a test can start and stop.

    Binds the HTTP port on construction, first -- so `address` is known, and a port in
    use is refused before anything else happens -- then the https listener, if asked for:
    one that will not bind turns the https page off (`https_off`), never the rig PC's
    page. It starts its threads in `start`: the telemetry thread (`_listen`), the command
    thread and, given a mark endpoint, the mark thread (each an `Outbox`, P4d-2b b2a),
    the HTTP server's loop, the https listener's loop and the keys thread, which asks
    wl.works only then (b2b-ready §3.2).

    `mark` is the session's mark endpoint, `--link`'s third; `None` without one, and
    then a mark is answered *not delivered* and the page greys its control.
    `allow_hosts` is `--allow-host`. `reply_timeout_s` and `connect_timeout_s` are
    the command sender's (`link.ZmqCommands`), passed so a test need not wait them.

    `gaze` is a demo's gaze endpoint, `--link`'s fourth (demo mode §4.5); given one, the gaze
    thread (an `Outbox` owning a `link.ZmqGaze`) pushes each report `Steering` forwards. `None`
    without one, and then a report is answered *not delivered*. `steady` is the clock the
    steer's hold is read on (`STEER_HOLD_S`), injectable so no test waits it.
    """

    def __init__(
        self,
        *,
        sub: str,
        req: str,
        http: tuple[str, int],
        token: str,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        keepalive_s: float = KEEPALIVE_S,
        receive_timeout_s: float = RECEIVE_TIMEOUT_S,
        mark: str | None = None,
        allow_hosts: tuple[str, ...] = (),
        reply_timeout_s: float = _link.REPLY_TIMEOUT_S,
        connect_timeout_s: float = _link.CONNECT_TIMEOUT_S,
        https: tuple[str, int] | None = None,
        tls: ssl.SSLContext | None = None,
        remote: Remote | None = None,
        https_off: str | None = None,
        gaze: str | None = None,
        steady: Callable[[], float] = _welfare.steady_seconds,
    ) -> None:
        if (https is None) != (tls is None) or (https is None) != (remote is None):
            raise ValueError(
                "https, tls and remote go together: the https listener needs its address, "
                "its TLS context and its sign-in, or none of them"
            )
        if https is not None and https_off is not None:
            raise ValueError("an https page cannot be both given and off")
        self.hub = Hub(endpoint=sub, marks=mark is not None, gaze=gaze is not None)
        self._sub = sub
        # `req` is not kept on `self`: nothing reads it after this constructor --
        # the command thread's `Outbox` closes over it directly (fix round 1,
        # housekeeping) -- and `_listen` connects no REQ socket of its own (b2a).
        self._receive_timeout_s = receive_timeout_s
        self._stop = threading.Event()
        #: The command thread (spec §5.3): it alone owns the REQ socket.
        self._commands = Outbox(
            "wlx-serve-commands",
            lambda: _link.ZmqCommands(req, reply_timeout_s, connect_timeout_s),
            COMMAND_QUEUE_DEPTH,
            self._stop,
        )
        #: The mark thread: it alone owns the PUSH socket to the mark endpoint, so a
        #: mark's signal never waits behind a command (spec §5.3). `None` without a
        #: mark endpoint.
        self._marks = (
            None
            if mark is None
            else Outbox(
                "wlx-serve-marks",
                lambda: _link.ZmqMarks(mark, connect_timeout_s),
                MARK_QUEUE_DEPTH,
                self._stop,
            )
        )
        #: The gaze thread (demo mode §4.5): it alone owns the PUSH socket to a demo's gaze
        #: endpoint, and `Steering` queues each report it forwards here, in order. `None`
        #: without a gaze endpoint, and so is `_steering`.
        self._gaze = (
            None
            if gaze is None
            else Outbox(
                "wlx-serve-gaze",
                lambda: _link.ZmqGaze(gaze),
                GAZE_QUEUE_DEPTH,
                self._stop,
                busy=GAZE_BUSY,
            )
        )
        self._steering = None if self._gaze is None else Steering(self._gaze, clock=steady)
        #: Each signalled mark's `(pressed_at, received_at)`, by number, for the note
        #: that follows it; the newest `MARKS_REMEMBERED`. HTTP threads share it.
        self._marked: OrderedDict = OrderedDict()
        self._marked_lock = threading.Lock()
        #: Set by `_listen` when the telemetry thread cannot go on -- a transport
        #: failure, never a bad frame (fix round 1, I1). `_wait` blocks on this
        #: alongside the operator's Ctrl-C, and `run` reads `_fatal_reason` once it
        #: wakes to say why, then closes and returns non-zero rather than serving on
        #: with a telemetry thread that is quietly gone.
        self._fatal = threading.Event()
        self._fatal_reason: str | None = None
        #: The full traceback behind `_fatal_reason` (fix round 2, M-c): the one
        #: line is what an operator needs; this is what the next session diagnosing
        #: an unfamiliar hub bug needs, and `_fatal_reason` alone was not going to
        #: be enough for that.
        self._fatal_traceback: str | None = None
        #: Why the rig's https page is off, or `None` while it serves or was never asked
        #: for (b2b-ready §3.1): from `run`'s setup, or set here when its port will not bind.
        self._https_off = https_off
        # The rig PC's page binds first: a port in use is refused before anything else
        # happens, and no https address can take it from the page (b2b-ready §3.1).
        self._http = ThreadingHTTPServer(
            http,
            make_handler(
                self.hub,
                token=token,
                stale_after_s=stale_after_s,
                keepalive_s=keepalive_s,
                hosts=box_names(allow_hosts),
                dispatch=self.dispatch,
                https_page=https is not None,
                https_off=https_off,
                steer=self.steer,
            ),
        )
        page_http = None
        if https is not None:
            try:
                page_http = _PageServer(
                    https,
                    make_handler(
                        self.hub, token=token, stale_after_s=stale_after_s,
                        keepalive_s=keepalive_s, dispatch=self.dispatch, remote=remote,
                        steer=self.steer,
                    ),
                    tls,
                )
            except OSError as exc:
                self._https_off = f"cannot serve https on {https[0]}:{https[1]}: {exc}"
                remote = None
                # `make_handler` builds a fresh class per call and nothing is served before
                # `start`, so the rig PC page's class can still learn the https page is off.
                self._http.RequestHandlerClass._https_page = False
                self._http.RequestHandlerClass._https_off = self._https_off
        self._page_http = page_http
        self._web = threading.Thread(
            target=self._http.serve_forever, name="wlx-serve-http", daemon=True
        )
        self._page_web = None if page_http is None else threading.Thread(
            target=page_http.serve_forever, name="wlx-serve-https", daemon=True
        )
        # wl.works is asked once `wlx serve` has bound, never before (b2b-ready §3.2).
        self._keys = None if remote is None else threading.Thread(
            target=remote.checker.keep_keys,
            args=(self._stop, lambda said: print(f"wlx serve: {said}", flush=True)),
            name="wlx-serve-keys", daemon=True,
        )
        self._telemetry = threading.Thread(
            target=self._listen, name="wlx-serve-telemetry", daemon=True
        )
        self._started = False
        self._closed = False

    @property
    def address(self) -> tuple[str, int]:
        """`(host, port)` as bound: the port the OS chose when `http` asked for 0."""
        host, port = self._http.server_address[:2]
        return host, port

    @property
    def https_off(self) -> str | None:
        """Why the rig's https page is off (b2b-ready §3.1); `None` while it serves or
        when it was never asked for."""
        return self._https_off

    @property
    def page_address(self) -> tuple[str, int] | None:
        """`(host, port)` of the https listener as bound; `None` without one."""
        if self._page_http is None:
            return None
        host, port = self._page_http.server_address[:2]
        return host, port

    def start(self) -> None:
        self._started = True
        self._telemetry.start()
        self._commands.start()
        if self._marks is not None:
            self._marks.start()
        if self._gaze is not None:
            self._gaze.start()
        self._web.start()
        if self._keys is not None:
            self._keys.start()
        if self._page_web is not None:
            self._page_web.start()

    def dispatch(self, request) -> tuple[int, dict]:
        """Send one parsed command (`parse_command`) and say what became of it.

        A `MarkSignal` goes to the mark thread, ahead of every command; the rest go
        to the command thread's queue (`wlx taskd`'s own -- `open`, `check`, `start`, `end` and
        `resume_session` -- answered with `SERVICE_SENT`), a `MarkNote` as the `link.Mark` it is, with
        the instants this process kept for that mark."""
        if isinstance(request, MarkSignal):
            return self._signal(request)
        if isinstance(request, _link.ManualReward):
            # Its own answers, never a re-send (PI, 2026-09-28): see `_rewarded`.
            return self._commands.submit(_rewarded(request))
        if isinstance(
            request,
            (
                _link.OpenSession,
                _link.CheckRun,
                _link.StartRun,
                _link.EndSession,
                _link.ResumeSession,
            ),
        ):
            return self._commands.submit(_delivered(request, SERVICE_SENT))
        if isinstance(request, MarkNote):
            pressed_at, received_at = self._recall(request.mark)
            request = _link.Mark(
                mark=request.mark,
                note=request.note,
                by=request.by,
                pressed_at=pressed_at,
                received_at=received_at,
            )
        return self._commands.submit(_delivered(request))

    def steer(self, report: GazeReport | GazeRelease) -> tuple[int, dict]:
        """**One `POST /gaze` past its checks** (demo mode §4.5): a release lets go of the
        steer; a report is answered 409 *not a demo* unless the latest frame is a demo
        session's (`Hub.demo_running`), *not delivered* by a console with no gaze endpoint,
        and is otherwise `Steering`'s to forward or not."""
        if isinstance(report, GazeRelease):
            return NOT_STEERING if self._steering is None else self._steering.release(report.page)
        if not self.hub.demo_running():
            return NOT_A_DEMO
        if self._steering is None:
            return not_delivered(NO_GAZE_ENDPOINT)
        return self._steering.report(report)

    def _signal(self, request: MarkSignal) -> tuple[int, dict]:
        """A mark's signal (spec §5.1, §5.3): a fresh number, the instant this
        process received it -- its own host clock, one of the record's three -- and
        the signal sent on the mark thread. Answered *signaled* with the number the
        page sends back with the note."""
        if self._marks is None:
            return not_delivered(_web.NO_MARK_ENDPOINT)
        number = secrets.randbelow(MARK_ID_LIMIT) + 1
        received_at = time.time()

        def work(marks) -> tuple[int, dict]:
            try:
                marks.signal(number)
            except _link.NotDelivered as exc:
                return not_delivered(str(exc))
            self._remember(number, request.pressed_at, received_at)
            return 200, {
                "status": "signaled",
                "mark": number,
                "said": "mark sent to the rig: type a note and press Enter, or Esc",
            }

        return self._marks.submit(work)

    def _remember(self, number: int, pressed_at: float | None, received_at: float) -> None:
        with self._marked_lock:
            self._marked[number] = (pressed_at, received_at)
            while len(self._marked) > MARKS_REMEMBERED:
                self._marked.popitem(last=False)

    def _recall(self, number: int) -> tuple[float | None, float | None]:
        with self._marked_lock:
            return self._marked.pop(number, (None, None))

    def _listen(self) -> None:
        """The telemetry thread: the one `ZmqConsole`, created, read and closed here,
        so its sockets have one owning thread (spec §2).

        **A frame this console cannot use is said, never shown and never fatal**
        (Review Focus 1): one that does not decode, and one of another schema --
        `link.decode` raises `link.FrameError` for both (`link.SchemaMismatch` is
        one), checked first thing every schema, before any other field is touched
        (fix round 1, I3). Either goes to `Hub.reject`, the page says why, and the
        last good frame stays.

        **A transport failure ends this thread, not silently** (fix round 1, I1).
        Before this fix, `ZmqConsole`'s own construction and every call in this loop
        sat outside any `try`, so a `--link` endpoint that parsed but that ZeroMQ
        itself refused (a bad port, a wildcard host connected-to rather than bound,
        an unknown scheme) raised out of this daemon thread, which `threading`
        prints to stderr and then quietly drops -- `wlx serve` kept its HTTP server
        up, `/health` kept saying `ok` on the last frame it ever got, forever. Now
        anything that is not a `TimeoutError` (an idle receive; expected, not an
        error) or a `FrameError` (a bad frame; said, not fatal) escapes this `with`
        block, is caught once below, and sets `_fatal` so `run` can end the process
        instead of serving on with a dead telemetry thread. Nothing here retries in
        a loop with no sleep: a fatal exception ends the thread on the first one,
        it does not spin.

        **A demo's screen, a `link.Drawn`, goes to `Hub.offer_drawn`, never `Hub.offer`**
        (demo mode §3.9), which reads a session's frame and would raise on it, ending this
        thread at a demo's first screen.
        """
        try:
            # Read-only (P4d-2b b2a): no REQ socket here. Commands are the command
            # thread's, so each socket has one owning thread (spec §2).
            with _link.ZmqConsole(
                self._sub, None, receive_timeout_s=self._receive_timeout_s
            ) as console:
                while not self._stop.is_set():
                    try:
                        frame = console.receive()
                    except TimeoutError:
                        continue
                    except _link.FrameError as exc:
                        self.hub.reject(str(exc))
                        continue
                    if isinstance(frame, _link.Drawn):
                        self.hub.offer_drawn(frame)
                    else:
                        self.hub.offer(frame)
        except Exception as exc:  # noqa: BLE001 -- ends the process, never hidden (I1)
            if self._stop.is_set():
                return  # asked to stop; a transport error on the way out is not new
            # fix round 3, M1: `_link._describe` (fix round 2, M-e) prints the
            # exception type alone when its own message is empty, instead of the
            # dangling "RuntimeError: " this line used to build inline -- the same
            # bug M-e fixed for `link.FrameError`, reachable here too.
            self._fatal_reason = _link._describe(exc)
            # fix round 2, M-c: the one-line reason is what an operator reads; the
            # full traceback is what diagnoses a hub bug nobody anticipated.
            self._fatal_traceback = traceback.format_exc()
            self._fatal.set()

    def close(self) -> None:
        """Stop serving, end every open stream, and close the `ZmqConsole`. Safe to
        call twice, and before `start`.

        **Fix round 2, N2.** `_http.shutdown()` blocks forever for a `serve_forever`
        loop that never ran at all (the stdlib's own docs on `shutdown()`), and
        `Thread.join()` raises `RuntimeError` on a thread that was never `.start()`-ed
        rather than returning -- both were reachable if a Ctrl-C landed inside
        `Server.start()` itself, between `self._telemetry.start()` and
        `self._web.start()`: `self._started` is set *before* either thread starts, so
        it cannot tell "both threads are up" from "one of them never got the chance."
        `Thread.ident` can: it stays `None` until a thread has actually begun running,
        and `.start()` itself blocks until `.ident` is set, so checking it here
        correctly separates "never started" from "already running" for the
        `shutdown()` deadlock and the `join()` `RuntimeError` above.

        **Fix round 3, M3: this does not cover every interleaving, and saying so
        plainly matters more than sounding finished.** A Ctrl-C landing during
        `Thread.start()`'s own internal startup wait (POSIX: `Thread._started.wait()`,
        called from inside `.start()` itself, a narrow window) can still leave that
        thread alive briefly after this method returns. That is not a hang -- the
        thread is a daemon and its own loop checks `_stop`, which is set above -- but
        it may print an exception traceback (for instance, from a socket this method
        has already closed underneath it) before it notices and exits.
        """
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self.hub.close()
        web_started = self._web.ident is not None
        telemetry_started = self._telemetry.ident is not None
        if web_started:
            self._http.shutdown()
        self._http.server_close()
        if self._page_http is not None:
            if self._page_web.ident is not None:
                self._page_http.shutdown()
            self._page_http.server_close()
        if web_started:
            self._web.join(timeout=5)
        if self._page_web is not None and self._page_web.ident is not None:
            self._page_web.join(timeout=5)
        if self._keys is not None and self._keys.ident is not None:
            self._keys.join(timeout=5)
        if telemetry_started:
            self._telemetry.join(timeout=5)
        # The outboxes stop on `_stop` too, answering anything still queued, and
        # close their sockets on their own threads (P4d-2b b2a; demo mode's gaze thread).
        for outbox in (self._commands, self._marks, self._gaze):
            if outbox is not None and outbox.thread.ident is not None:
                outbox.thread.join(timeout=5)


def _git_checkout_containing(path: Path) -> Path | None:
    """The nearest ancestor of `path` (`path` itself included) with a `.git` entry --
    file or directory -- or `None` if none of them has one.

    **Fix round 1, M1.** `_REPO_ROOT`, computed from `Path(__file__)`, is somewhere
    under `site-packages` for a non-editable install of `wl_xcon` -- and
    `read_token`'s "inside this repository" refusal, checked with
    `resolved.is_relative_to(_REPO_ROOT)`, then guards nothing there: no token file
    written into a real git checkout is ever *inside* a `site-packages` directory. Its
    own test computed `_REPO_ROOT` the identical way, so it agreed with the check
    regardless of whether that path was a real repository, which is why the test kept
    passing while the check itself guarded nothing.

    Walking up from the token path instead finds any git checkout wherever it
    actually is -- **a file counts, not only a directory**, because a worktree's
    `.git` is a file naming the real one elsewhere (this repository's own worktrees,
    this session's own worktree among them, are exactly this case)."""
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def read_token(path: Path) -> str:
    """The `/health` bearer token: from a file, never from the repository (spec §2).

    Refused, each with a sentence and before anything binds: a file inside this
    checkout -- one `git add` from public -- a file that cannot be read, an empty one
    (there is no default token), one holding a non-ASCII character, which
    `hmac.compare_digest` cannot compare, so every request would fail, the correct
    one included (wl-preproc refuses the same), and one holding a newline or other
    control character no HTTP header can carry (fix round 1, M2). The whitespace
    around it -- the newline an editor leaves -- is not part of the token.
    """
    resolved = path.expanduser().resolve()
    checkout = _git_checkout_containing(resolved)
    if checkout is not None:
        raise SystemExit(
            f"refused: the /health token file {str(path)!r} is inside this repository "
            f"({checkout}), one `git add` from being published; keep it outside any "
            f"checkout (P4d-2b spec §2: a token file, never the repository)"
        )
    try:
        token = resolved.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(
            f"refused: cannot read the /health token file {str(path)!r}: {exc}"
        ) from exc
    if not token:
        raise SystemExit(
            f"refused: the /health token file {str(path)!r} is empty; there is no "
            f"default token, so wl-works could never authenticate -- write one token "
            f"on one line"
        )
    if not token.isascii():
        raise SystemExit(
            "refused: the /health token contains a non-ASCII character; "
            "hmac.compare_digest cannot compare it, which would make every request "
            "fail authentication, the correct one included"
        )
    if not token.isprintable():
        raise SystemExit(
            "refused: the /health token cannot be carried in a header: it contains "
            "a newline or other control character (a token file with a second line, "
            "for example); write it on one line with nothing else in the file"
        )
    return token


def parse_link(text: str) -> tuple[str, str, str | None, str | None]:
    """`PUB,REP`, `PUB,REP,MARK` or `PUB,REP,MARK,GAZE`, exactly as `wlx run --link` or `wlx
    taskd --link` takes it (P4d-2b b2a added the third, demo mode the fourth, §3.8): telemetry
    is read from the first, commands are sent to the second, mark signals to the third, and a
    demo's pointer reports to the fourth (`POST /gaze`), each of the last two `None` when not
    given.

    **Fix round 1, I1(a).** This used to check only that each half contained
    `"://"` somewhere, which is what its docstring already claimed to do and did
    not: `"tcp://127.0.0.1:5571, tcp://127.0.0.1:5572"` (a space after the comma,
    the security review's own reproduction) passed it, and the leading space rode
    along into `ZmqConsole.connect()` inside the telemetry thread, where ZeroMQ
    refused it -- a traceback on a daemon thread instead of a sentence here.
    `tcp://127.0.0.1:abc`, `tcp://127.0.0.1` (no port), `tcp://*:5571` and
    `foo://...` all passed the same way.

    Now each endpoint is stripped and required to be `tcp://HOST:PORT`, PORT a
    decimal number from 1 to 65535, HOST anything but empty or `*` -- a console
    *connects*; it never binds, so a wildcard bind address is never what it means
    (`link.ZmqConsole`'s own docstring makes the same distinction from
    `link.ZmqLink`). Only `tcp://` -- neither `wlx run --link` nor `wlx console
    --sub/--req` (`cli.py`) restrict a `--link`/`--sub`/`--req` value to a
    transport at all before handing it to `ZmqLink`/`ZmqConsole`, and nothing in
    this codebase's tests exercises `ipc://`/`inproc://` through either of those
    end to end (only `link._binds_beyond_this_machine`'s own classification test
    does, and only on the *bind* side); accepting them here without an end-to-end
    check anywhere would be inventing support this parser cannot verify.
    """
    parts = [part.strip() for part in text.split(",")]
    if len(parts) not in (2, 3, 4) or not all(parts):
        raise SystemExit(
            f"refused: --link expects PUB,REP, PUB,REP,MARK or PUB,REP,MARK,GAZE -- two, three "
            f"or four comma-separated endpoints such as tcp://127.0.0.1:5571, as given to "
            f"`wlx run --link` or `wlx taskd --link` -- got {text!r}"
        )
    for endpoint in parts:
        _refuse_unless_tcp_endpoint(endpoint, text)
    mark = parts[2] if len(parts) >= 3 else None
    gaze = parts[3] if len(parts) == 4 else None
    return parts[0], parts[1], mark, gaze


def _refuse_unless_tcp_endpoint(endpoint: str, whole: str) -> None:
    """One `--link` endpoint, already stripped: `tcp://HOST:PORT` or a `SystemExit`
    naming exactly what is wrong with it, before anything connects (fix round 1,
    I1(a))."""
    scheme, sep, rest = endpoint.partition("://")
    if not sep or scheme != "tcp":
        raise SystemExit(
            f"refused: --link endpoint {endpoint!r} (in {whole!r}) must be "
            f"tcp://HOST:PORT"
        )
    host, colon, port = rest.rpartition(":")
    if not colon or not host:
        raise SystemExit(
            f"refused: --link endpoint {endpoint!r} is missing a port -- expected "
            f"tcp://HOST:PORT"
        )
    if host == "*":
        raise SystemExit(
            f"refused: --link endpoint {endpoint!r} names a wildcard host; a "
            f"console connects, it never binds, so give the box's own address "
            f"or name instead"
        )
    # M3's `isascii()`-and-`isdecimal()` fix applies here for the same reason:
    # `str.isdigit()` accepts characters `int()` does not.
    if not port.isascii() or not port.isdecimal() or not (1 <= int(port) <= 65535):
        raise SystemExit(
            f"refused: --link endpoint {endpoint!r}'s port must be a decimal "
            f"number from 1 to 65535"
        )


def parse_http(text: str, flag: str = "--http") -> tuple[str, int]:
    """`HOST:PORT`, IPv4 or a name: the stdlib server here binds IPv4 only. `flag` names
    the option in the refusal."""
    host, sep, port = text.rpartition(":")
    if (
        not sep
        or not host
        or ":" in host
        or host.startswith("[")
        # fix round 1, M3: `str.isdigit()` accepts characters `int()` does not --
        # `"²"` (superscript two) is a digit by Unicode's reckoning and raised
        # a bare `ValueError` traceback out of `int(port)` below instead of this
        # sentence. `isascii() and isdecimal()` is the pair `int()` itself agrees
        # with.
        or not port.isascii()
        or not port.isdecimal()
        or int(port) > 65535
    ):
        if flag != "--http":
            raise SystemExit(
                f"refused: {flag} expects HOST:PORT with an IPv4 address or a name, "
                f"such as 0.0.0.0:8443 -- got {text!r}"
            )
        raise SystemExit(
            f"refused: --http expects HOST:PORT with an IPv4 address or a name -- "
            f"127.0.0.1:8080 for this box only, 0.0.0.0:8080 to let the lab network "
            f"read the page -- got {text!r}"
        )
    return host, int(port)


def _wait(server: Server) -> None:
    """Block until the operator interrupts, or the telemetry thread cannot go on
    (fix round 1, I1). Its own function so a test can stand in for the person
    pressing Ctrl-C, and returns on its own once `server._fatal` is set -- which
    is the only way this can return without `KeyboardInterrupt`, so `run` tells
    the two apart by whether an exception came out of this call.

    **Fix round 2, M-b; fix round 3, M2 (its docstring contradicted itself, and
    this rewrite is the fix for that too -- CLAUDE.md: no fabrication).** On
    POSIX, a real SIGINT ends a serving `wlx serve` with 130:
    `test_wlx_serve_exits_130_on_a_real_sigint` starts one as its own process, with
    this function unpatched, fetches its page and sends the signal. That is the only
    test that does; every other Ctrl-C test raises `KeyboardInterrupt` through a
    monkeypatch, which shows `run`'s handling and not that the signal arrives.
    **Windows is UNVERIFIED here**: a blocking `Event.wait()` with no timeout is
    documented elsewhere as not reliably interruptible by Ctrl-C on that platform
    (a wait with no timeout never returns control to the interpreter for a signal
    to be noticed there), but nothing in this repository has measured it. Waiting
    in a loop with a short timeout -- checked and abandoned once a second, never
    once forever -- is the portable form regardless of which platform's claim
    turns out to hold, at the cost of a wake-up this process is not otherwise
    doing anything with. Not a measurement of this system either way.
    """
    while not server._fatal.wait(1.0):
        pass


class _HttpsOff(Exception):
    """Why the rig's https page is off: one sentence, never a refusal of `wlx serve`
    (b2b-ready §3.1)."""


def _https_setup(args, flags: dict) -> tuple:
    """The https listener's page, address, TLS and sign-in, from the six flags (b2b spec
    §3), as `(page, listener)`. A setup that cannot be completed raises `_HttpsOff` with
    its sentence: the https page is off, and the rig PC's page serves regardless
    (b2b-ready §3.1). wl.works is not asked here: the keys thread asks it once `wlx
    serve` has bound (§3.2)."""
    missing = [flag for flag, value in flags.items() if value is None]
    if missing:
        raise _HttpsOff(
            f"it needs all six of --https, --tls-cert, --tls-key, --rig-page, "
            f"--wl-works-issuer and --wl-works-cache together; missing {', '.join(missing)}"
        )
    needs_extra = (
        "--https needs the signin extra (PyJWT with cryptography), which is not installed"
    )
    try:
        import jwt  # only in this branch: a rig without the `signin` extra runs `serve`
    except ImportError as exc:
        if exc.name == "jwt":
            raise _HttpsOff(needs_extra) from None
        # Installed but broken, which is never called "not installed" (b2b slice 2): PyJWT
        # 2.10.1 catches only `ModuleNotFoundError` around its `cryptography` import, so a
        # `cryptography` that is there and will not load arrives here. Named by its type and
        # module, never by its text, which may carry a path.
        source = f" from {exc.name}" if exc.name else ""
        raise _HttpsOff(
            f"the signin extra is installed but could not be loaded ({type(exc).__name__}{source})"
        ) from None
    if not jwt.algorithms.has_crypto:
        # PyJWT imports without `cryptography`, and then skips every RSA key.
        raise _HttpsOff(needs_extra)
    from wl_xcon import signin
    try:
        page = signin.parse_rig_page(args.rig_page)
        issuer = signin.parse_issuer(args.wl_works_issuer)
    except ValueError as exc:
        raise _HttpsOff(str(exc)) from None
    try:
        https = parse_http(args.https, "--https")
        tls = tls_context(args.tls_cert, args.tls_key)
    except SystemExit as refused:
        raise _HttpsOff(str(refused.code).removeprefix("refused: ")) from None
    checker = signin.Checker(page=page, issuer=issuer, cache=args.wl_works_cache)
    return page, {"https": https, "tls": tls, "remote": Remote(page, checker)}


def run(args) -> int:
    """`wlx serve`: check everything, bind, serve until interrupted (spec §2).

    The rig PC page's own setup is refused before anything else binds (its port is bound
    first), each refusal a sentence.
    The https page's never is: a setup that cannot be completed turns the https page off,
    says why in the terminal and on the rig PC's page, and the rig PC's page serves
    regardless (b2b-ready §3.1).
    Ctrl-C ends it with 130, as `wlx console` does, and says what it did not stop.
    A telemetry thread that cannot go on ends it too (fix round 1, I1): `_wait`
    returns on its own rather than raising, so it is distinguished from Ctrl-C by
    `server._fatal` being set, and this returns 1 with a sentence naming why --
    the session on the box is unaffected either way; this is the console's own
    process, and closing it commands nothing.
    """
    token = read_token(args.health_token_file)
    sub, req, mark, gaze = parse_link(args.link)
    host, port = parse_http(args.http)
    stale_after = (
        DEFAULT_STALE_AFTER_S if args.stale_after is None else args.stale_after
    )
    if not math.isfinite(stale_after) or stale_after <= 0:
        raise SystemExit(
            f"refused: --stale-after must be a positive number of seconds, got "
            f"{args.stale_after!r}"
        )
    listener: dict = {}
    remote_flags = {
        "--https": args.https,
        "--tls-cert": args.tls_cert,
        "--tls-key": args.tls_key,
        "--rig-page": args.rig_page,
        "--wl-works-issuer": args.wl_works_issuer,
        "--wl-works-cache": args.wl_works_cache,
    }
    page = None
    https_off = None
    if any(value is not None for value in remote_flags.values()):
        try:
            page, listener = _https_setup(args, remote_flags)
        except _HttpsOff as off:
            https_off = str(off)
    try:
        server = Server(
            sub=sub,
            req=req,
            http=(host, port),
            token=token,
            stale_after_s=stale_after,
            mark=mark,
            allow_hosts=tuple(args.allow_host),
            https_off=https_off,
            gaze=gaze,
            **listener,
        )
    except OSError as exc:
        raise SystemExit(f"refused: cannot serve on {host}:{port}: {exc}") from exc
    # fix round 1, M5: `server.start()` and the startup print used to sit after this
    # `try`, so a Ctrl-C landing between construction and `_wait` escaped as a bare
    # `KeyboardInterrupt` traceback instead of the 130 this function promises
    # everywhere else. Both are inside it now.
    try:
        server.start()
        bound_host, bound_port = server.address
        box = f"this box's own browser at http://127.0.0.1:{bound_port}/"
        controls = (
            f"controls work only from {box}"
            if server.page_address is None
            else f"controls work from {box}, and from the rig's https page at {page.page} "
            f"for people signed in to wl.works"
        )
        if server.https_off is not None:
            print(f"wlx serve: {_web.HTTPS_OFF}: {server.https_off}", flush=True)
        at = _console_at(bound_host, bound_port, socket.gethostname())
        print(
            f"wlx serve: the console is at {at}, reading "
            f"{sub}, sending commands to {req}, marks to "
            f"{mark or 'nowhere (no MARK endpoint given)'} and a demo's pointer reports to "
            f"{gaze or 'nowhere (no GAZE endpoint given)'}; {controls}; GET /health "
            f"needs the bearer token",
            flush=True,
        )
        _wait(server)
    except KeyboardInterrupt:
        print(
            "serve: interrupted -- the session keeps running on the box; nothing here "
            "stops it",
            file=sys.stderr,
        )
        return 130
    finally:
        server.close()
    if server._fatal.is_set():
        print(
            f"wlx serve: the telemetry thread stopped: {server._fatal_reason}; "
            f"the session is unaffected",
            file=sys.stderr,
        )
        # fix round 2, M-c: the traceback behind the one-line reason, for whoever
        # has to diagnose a hub bug the sentence alone cannot explain.
        if server._fatal_traceback:
            print(server._fatal_traceback, file=sys.stderr)
        return 1
    return 0
