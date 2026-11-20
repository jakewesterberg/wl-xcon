"""The rig's https page, driven in a real browser (b2b spec §8; closes XC-186).

The page's script was tested by reading its text, which let two of b3a-2's defects
through. These tests run it: a real browser (Chromium; `WLX_BROWSER=webkit` for WebKit) signs in against a fake wl.works served over https
(`_browser.FakeWlWorks`), and the rig is a real `_PageServer` with a real
`signin.Checker`; only the dispatch behind `/commands` is a stand-in.

Run with `WLX_REQUIRE_BROWSER=1` in CI, where a missing browser fails instead of skipping.
**No token is ever put in a failing assertion**: each check computes a bool first, because
pytest prints both operands of a failing `==`.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import threading
import time
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from datetime import date
from http.server import ThreadingHTTPServer

import pytest

from _browser import REQUIRED, FakeWlWorks, browser  # noqa: E402

try:
    import jwt  # noqa: F401
except ImportError:
    if REQUIRED:
        raise
    pytest.skip("PyJWT is not installed (the signin extra)", allow_module_level=True)

from _demo import ANSWERED_STATES, FIX, FIXATED_STATES, REST, Demo, shown_names, target  # noqa: E402
from _frames import ENDPOINT, frame, idle  # noqa: E402
from _issuer import Issuer  # noqa: E402
from _ports import endpoints as free_endpoints  # noqa: E402
from _rig import DIRECT, RIG, STEREOSCOPE  # noqa: E402
from _tls import client_context, material  # noqa: E402
from wl_xcon import demoscreen, pointer, serve, signin, viewport, warnlist, web  # noqa: E402
from wl_xcon import screen as screens  # noqa: E402
from wl_xcon.findings import SESSION_KINDS  # noqa: E402
from wl_xcon.link import (  # noqa: E402
    SCHEMA, BackBlock, CheckRun, ClearOwed, Decline, Drawn, Drum, ManualReward, NextBlock,
    OpenSession, Pause, Pooled, PoolRow, Preflight, PreflightItem, SetParameter, Shaping, StageRow,
    StaircaseRow, StartRun, Suggestion, Training, WarningRow,
)
from wl_xcon.photometry import SRGB, Gray  # noqa: E402
from wl_xcon.warnlist import HEAD_FREE  # noqa: E402
from wl_xcon.serve import (  # noqa: E402
    GazeRelease, GazeReport, Hub, Remote, Server, _PageServer, make_handler, tls_context,
)
from wl_xcon.task import Disc, Outcome, Stimulus, Trial  # noqa: E402

TOKEN = "t0ken-for-tests"
#: Housekeeping, not measurements: how long a wait may take before the test fails.
WAIT_S = 10.0
SIGNED_IN = "#member:has-text('Jake Westerberg (wl.works)')"
PAUSE = '[data-cmd="pause"]'
REWARD = '[data-cmd="reward"]'


class _Clock:
    def __call__(self) -> float:
        return 0.0


class _Dispatch:
    """What `Server.dispatch` would be. A `ManualReward` waits on `gate` when one is set."""

    def __init__(self) -> None:
        self.seen: list = []
        self.gate: threading.Event | None = None
        self.entered = threading.Event()
        #: A server fault after the command was handed over (XC-042): the backstop answers 500.
        self.raises = False
        #: The (status, body) the rig answers every command with, when set.
        self.answers: tuple[int, dict] | None = None
        #: Seconds the rig takes to answer, as it does until its next trial boundary.
        self.delay = 0.0

    def __call__(self, request):
        self.seen.append(request)
        if self.delay:
            time.sleep(self.delay)
        if isinstance(request, ManualReward) and self.gate is not None:
            self.entered.set()
            self.gate.wait(timeout=20.0)  # bounded: a failing test must not hang its teardown
        if self.raises:
            raise RuntimeError("a fault the server did not anticipate")
        if self.answers is not None:
            return self.answers
        return 200, {"status": "sent", "said": "sent: test"}


#: **A box acted on through a selector is opened in its tab's editor first** (`_Opening`; the
#: summary and editor design of 2026-11-19): the setting's summary line clicked, as a person does,
#: by the line's own `click()`, so no pointer press holds a frame the test is timing. The box the
#: selector's first match stands in; nothing where it is open already, stands in none, or is not
#: there yet (an action waits for it, as Playwright's would, up to `WAIT_S`). A pinned copy in
#: Runtime's editor is opened by its pinned line, as a person opens it (the build's Task 3).
_OPEN_ITS_BOX = """(selector) => {
  let node = null;
  try { node = document.querySelector(selector); } catch (e) { return "not css"; }
  if (!node) { return "none"; }
  const box = node.closest("#params > .editing > .box, #training-params > .editing > .box, " +
    "#pinned-editing > .box[data-pin]");
  if (!box || !box.hidden) { return "shown"; }
  const name = box.getAttribute("data-card") || box.getAttribute("data-pin");
  const line = Array.from(box.parentNode.parentNode.querySelectorAll(
    ":scope > .summary .line[data-open]")).find((one) => one.getAttribute("data-open") === name);
  if (!line) { return "no line"; }
  line.click();
  return box.hidden ? "still hidden" : "opened";
}"""


class _Opening:
    """**A Playwright page whose actions on a setting's box open it first** (the summary and
    editor design of 2026-11-19: every box stays as it was, in an editor that shows the one
    opened): a click, a fill, a key, a focus, a hover, a tick, a visibility read or a wait for a
    box to be shown, given a selector whose first match stands in a box of `#params`' or
    `#training-params`' editor, clicks that box's summary line first (`_OPEN_ITS_BOX`), so every test of a box's behavior reads as it did
    on the grid and goes through the line a person uses. Everything else is the page's own."""

    _ACTS = frozenset({"click", "dblclick", "fill", "press", "focus", "check", "uncheck", "hover",
                       "type", "select_option", "set_checked", "tap", "is_visible",
                       "wait_for_selector"})
    _WAITS = frozenset({"click", "dblclick", "fill", "press", "focus", "check", "uncheck", "hover",
                        "type", "select_option", "set_checked", "tap", "wait_for_selector"})

    def __init__(self, page) -> None:
        object.__setattr__(self, "_page", page)

    #: What a document going away under `_OPEN_ITS_BOX` says (WebKit's and Chromium's words): a
    #: page navigating -- a reload the test waits through, as XC-227's does -- has no box to open
    #: yet, so it is "none", and the wait goes on in the next document.
    _GONE = ("Execution context was destroyed", "Cannot find context with specified id",
             "Frame was detached", "Target closed")

    def _opening(self, selector: str) -> str:
        """`_OPEN_ITS_BOX` on `selector`, a navigation under it read as nothing there yet (the
        summary and editor build's Task 3: the WebKit sign-in reload flake's first cause, this
        poll's `evaluate` landing in a document the reload was tearing down)."""
        from playwright.sync_api import Error

        try:
            return self._page.evaluate(_OPEN_ITS_BOX, selector)
        except Error as error:
            if any(said in str(error) for said in self._GONE):
                return "none"
            raise

    def __setattr__(self, name, value) -> None:
        setattr(self._page, name, value)

    def __getattr__(self, name):
        attr = getattr(self._page, name)
        if name not in self._ACTS or not callable(attr):
            return attr

        def acting(selector, *args, **kwargs):
            if isinstance(selector, str) and kwargs.get("state", "visible") == "visible":
                waits = kwargs.get("timeout", WAIT_S * 1000) / 1000 if name in self._WAITS else 0
                end = time.monotonic() + waits
                while self._opening(selector) == "none" and time.monotonic() < end:
                    self._page.wait_for_timeout(50)
            return attr(selector, *args, **kwargs)

        return acting


class _Rig:
    def __init__(self, tmp_path, browser, *, keys: bool = True, gaze: bool = False) -> None:
        self._browser = browser
        self._contexts: list = []
        self._thread = None
        self.fake = None
        self.dispatch = _Dispatch()
        #: What `Server.steer` would be, for a demo's pointer (`gaze`: a console with the
        #: demo's gaze endpoint; demo mode's Task 9).
        self.steer = _Steer()
        self.hub = Hub(steady=_Clock(), endpoint=ENDPOINT, gaze=gaze)
        try:
            tls = material(tmp_path)
            self.context = client_context(tls["ca"])
            rig_port, fake_port = (int(item.rsplit(":", 1)[1]) for item in free_endpoints(2))
            self.port = rig_port
            self.page_url = f"https://127.0.0.1:{rig_port}/"
            self.origin = f"https://127.0.0.1:{rig_port}"
            self.issuer = Issuer(issuer=f"https://127.0.0.1:{fake_port}/api/auth")
            self.fake = FakeWlWorks(self.issuer, self.page_url, self.origin, tls, fake_port)
            self.fake.start()
            self.hub.offer(frame())
            rig_page = signin.parse_rig_page(f"rig-3={self.page_url}")
            self.checker = signin.Checker(
                page=rig_page, issuer=self.issuer.issuer, cache=tmp_path / "wl-works.json", fetch=self.issuer.fetch
            )
            if keys:
                self.checker.load()
            self.server = _PageServer(
                ("127.0.0.1", rig_port),
                make_handler(
                    self.hub, token=TOKEN, stale_after_s=30.0, dispatch=self.dispatch,
                    remote=Remote(rig_page, self.checker), steer=self.steer,
                ),
                tls_context(tls["cert"], tls["key"]),
            )
            self._thread = threading.Thread(
                target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
            )
            self._thread.start()
        except BaseException:
            self.close()
            raise

    def browser_page(self):
        """A Playwright page, in a context of its own, already at the rig's page."""
        context = self._browser.new_context(ignore_https_errors=True)
        self._contexts.append(context)
        page = _Opening(context.new_page())
        page.set_default_timeout(WAIT_S * 1000)
        page.goto(self.page_url)
        assert page.evaluate("window.isSecureContext"), "the page is not a secure context"
        return page

    def wait_for(self, predicate, seconds: float = WAIT_S) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.05)
        pytest.fail(f"timed out after {seconds:g} s waiting for {getattr(predicate, '__name__', 'a condition')}")

    def close(self) -> None:
        """Everything this rig opened, each step guarded so one failure leaves the rest."""
        for context in self._contexts:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            if self.dispatch.gate is not None:
                self.dispatch.gate.set()
            self.hub.close()
        finally:
            try:
                if self._thread is not None:
                    self.server.shutdown()
                    self.server.server_close()
                    self._thread.join(timeout=5)
            finally:
                if self.fake is not None:
                    self.fake.stop()


@pytest.fixture
def rig(tmp_path):
    with browser() as launched:
        made = _Rig(tmp_path, launched)  # closes what it opened itself if it fails
        try:
            yield made
        finally:
            made.close()


@pytest.fixture
def rig_without_keys(tmp_path):
    """A rig whose checker has not loaded: the page it serves first can offer no sign-in."""
    with browser() as launched:
        made = _Rig(tmp_path, launched, keys=False)
        try:
            yield made
        finally:
            made.close()


def _stored(page) -> dict | None:
    return page.evaluate("JSON.parse(window.sessionStorage.getItem('wlx-signin') || 'null')")


def _has_signin(page) -> bool:
    """Whether sessionStorage holds a sign-in. A bool, never the record: it holds tokens."""
    return page.evaluate("window.sessionStorage.getItem('wlx-signin') !== null")


def _sign_in(page) -> None:
    page.click("#signin")
    page.wait_for_selector(SIGNED_IN, timeout=WAIT_S * 1000)


def _post(rig, path: str, access: str):
    import http.client

    connection = http.client.HTTPSConnection("127.0.0.1", rig.port, timeout=5, context=rig.context)
    try:
        connection.putrequest("POST", path, skip_host=True)
        for name, value in {
            "Host": f"127.0.0.1:{rig.port}", "Origin": rig.origin,
            "Content-Type": "application/json", "Authorization": "Bearer " + access,
            "Content-Length": "2",
        }.items():
            connection.putheader(name, value)
        connection.endheaders(b"{}")
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _until(page, expression: str, seconds: float = WAIT_S) -> None:
    """Wait until `expression` is true in the page, asking it again every 50 ms (housekeeping).
    Not `wait_for_function`: its polling evaluates a string with `eval`, which the page's
    Content-Security-Policy refuses."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if page.evaluate(expression):
            return
        page.wait_for_timeout(50)  # lets Playwright answer the page's routed requests meanwhile
    pytest.fail(f"timed out after {seconds:g} s waiting for {expression}")


def _more(page, root: str = "#params") -> None:
    """**Open every box's *more* in `root`** as a person does, by its summary (the console
    interface rework's Task 5: *hand back*, a draw's live numbers and *change the range* sit in a
    box's *more*); the page keeps each open across the frames that replace the boxes."""
    names = page.eval_on_selector_all(
        f"{root} .box", "boxes => boxes.map((box) => box.getAttribute('data-card'))")
    for name in names:
        page.click(f'{root} .box[data-card="{name}"] > details.more > summary')
        page.wait_for_selector(f'{root} .box[data-card="{name}"] > details.more[open]',
                               state="attached")


def _pauses(rig) -> list:
    return [seen for seen in rig.dispatch.seen if isinstance(seen, Pause)]


def _rewards(rig) -> list:
    return [seen for seen in rig.dispatch.seen if isinstance(seen, ManualReward)]


def test_a_member_signs_in_and_a_pause_reaches_the_rig_as_theirs(rig):
    page = rig.browser_page()
    page.click("#signin")
    page.wait_for_selector(SIGNED_IN, timeout=10_000)
    no_code = "code=" not in page.url  # a bool: a failing assert would print the URL
    assert no_code
    page.click(PAUSE)
    rig.wait_for(lambda: rig.dispatch.seen)
    assert isinstance(rig.dispatch.seen[-1], Pause)
    assert rig.dispatch.seen[-1].by.name == "Jake Westerberg"


def test_a_member_clears_a_trial_and_switches_drumming_and_each_reaches_the_rig_as_theirs(rig):
    """Engine build C2a: *clear one* and *clear the rest* on a condition of the Still-needed pane
    send that condition, a drumming switch its scope, and a training switch its setting, each as
    the signed-in member's (the PI, 2026-10-11 and 2026-10-18; the rest, the science review's D5).
    *Clear* is offered while its training aid is on."""
    rig.hub.offer(frame(clearing=True))
    page = rig.browser_page()
    page.click("#signin")
    page.wait_for_selector(SIGNED_IN, timeout=10_000)

    page.click('[data-cmd="clear"][data-condition="ecc 10"]:not([data-rest])')
    rig.wait_for(lambda: rig.dispatch.seen)
    page.click('[data-cmd="clear"][data-condition="ecc 10"][data-rest]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    page.click('[data-cmd="drum"][data-scope="run"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 3)
    page.click('[data-cmd="training"][data-setting="first_answers"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 4)

    one, rest, drummed, setting = rig.dispatch.seen
    member = "Jake Westerberg"
    assert (type(one), one.condition, one.rest, one.by.name) == (ClearOwed, "ecc 10", False, member)
    assert (type(rest), rest.condition, rest.rest, rest.by.name) == (
        ClearOwed, "ecc 10", True, member)
    assert (type(drummed), drummed.scope, drummed.by.name) == (Drum, "run", member)
    assert (type(setting), setting.setting, setting.on, setting.by.name) == (
        Training, "first_answers", True, member)


def test_a_double_click_on_clear_one_clears_one_trial_and_a_training_switch_goes_off_as_well(rig):
    """Important 1 of Task 9's fix round: a double click, or two quick clicks, on *clear one* sent
    two commands; the page holds a second clear of the same button as it does a reward's. And the
    switch goes *off* as well as on."""
    rig.hub.offer(frame(clearing=True))
    page = rig.browser_page()
    page.click("#signin")
    page.wait_for_selector(SIGNED_IN, timeout=10_000)
    one = '[data-cmd="clear"][data-condition="ecc 10"]:not([data-rest])'

    page.dblclick(one)
    rig.wait_for(lambda: rig.dispatch.seen)
    page.click(one)  # a quick second click, as the button stays until the next trial boundary
    time.sleep(0.5)  # housekeeping: room for a wrong second send to arrive
    assert [type(seen) for seen in rig.dispatch.seen] == [ClearOwed]

    page.click('[data-cmd="training"][data-setting="clear"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    off = rig.dispatch.seen[1]
    assert (type(off), off.setting, off.on) == (Training, "clear", False)


def test_a_state_that_was_not_started_here_is_refused(rig):
    page = rig.browser_page()
    # A sign-in this tab did start, with a state of its own; the return carries another.
    page.evaluate(
        "window.sessionStorage.setItem('wlx-signin-pkce', JSON.stringify({verifier: 'v', state: 'real'}))"
    )
    page.goto(rig.page_url + "?code=X&state=forged")
    page.wait_for_selector("#sent:has-text('this sign-in was not started from this page')")
    assert rig.fake.attempts == 0  # the page never even asked wl.works
    assert rig.fake.exchanges == 0
    assert page.inner_text("#member") == ""
    assert not _has_signin(page)


def test_a_short_token_is_renewed_before_a_command(rig):
    # Housekeeping, from web.py's `FRESH_FOR_MS` (60 s) and `scheduleRenew` (half of what
    # is left, when under `RENEW_BEFORE_MS`): 64 s at sign-in, 6 s waited, so about 58 s
    # are left -- inside the 60 s a command renews for -- while the tab's own timer, at
    # about 32 s, is far off. Only the command's `fresh()` can renew here.
    rig.fake.expires_in = 64
    page = rig.browser_page()
    _sign_in(page)
    time.sleep(6)
    assert rig.fake.renewals == 0
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert rig.fake.renewals == 1
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)"


def test_a_refused_renewal_signs_the_page_out_with_wl_works_sentence(rig):
    rig.fake.expires_in = 4
    page = rig.browser_page()
    _sign_in(page)
    rig.fake.refuse_renewal = True
    page.wait_for_selector("#sent:has-text('24 hours old')")
    assert page.is_disabled(PAUSE)
    assert page.inner_text("#member") == ""
    assert not _has_signin(page)


def test_sign_out_makes_the_rig_refuse_the_old_token(rig):
    page = rig.browser_page()
    _sign_in(page)
    access = _stored(page)["access"]
    page.click("#signout")
    # wl.works stays signed in, and the next sign-in goes straight through as the same member
    # (spec §2): the sentence says so, for a shared browser (the final review, M6).
    assert page.inner_text("#sent") == (
        "signed out at this rig; wl.works is still signed in as Jake Westerberg, so anyone "
        "else using this browser must sign out of wl.works there first"
    )
    seen: list = []

    def refused() -> bool:
        seen[:] = [_post(rig, "/whoami", access)]
        return seen[0][0] == 401

    rig.wait_for(refused)
    assert seen[0][1]["reason"] == "signed_out"
    assert page.is_disabled(PAUSE)


def test_a_reward_refused_for_its_token_is_not_sent_again(rig):
    rig.hub.offer(frame(paused_at=1_700_000_030.0))
    page = rig.browser_page()
    _sign_in(page)
    rig.wait_for(lambda: not page.is_disabled(REWARD))
    rig.checker.sign_out("Bearer " + _stored(page)["access"])
    page.click(REWARD)
    page.wait_for_selector("#sent:has-text('signed out here')")
    time.sleep(2)  # housekeeping: long enough for a wrong second send to arrive
    assert len(_rewards(rig)) == 0  # a count: a failing assert would print the actor's token id
    assert page.inner_text("#member") == ""


def test_neither_the_code_nor_the_token_reaches_the_page_server_log(rig, capfd):
    page = rig.browser_page()
    _sign_in(page)
    access = _stored(page)["access"]
    refresh = _stored(page)["refresh"]
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    logged = capfd.readouterr().err
    assert rig.fake.codes
    leaked = sum(1 for secret in (*rig.fake.codes, access, refresh) if secret in logged)
    assert leaked == 0  # a count: never the values


#: Counts, in the page, the renewals it asks wl.works for and the clicks it has handled. A
#: listener on `window` runs after the page's own on `document`, so a count of clicks there
#: means the page's handler for that click has finished.
_COUNTS = """
window.__renewals = 0;
window.__clicks = 0;
(function () {
  var real = window.fetch;
  window.fetch = function (url, init) {
    if (init && typeof init.body === "string" && init.body.indexOf("grant_type=refresh_token") >= 0) {
      window.__renewals += 1;
    }
    return real.apply(this, arguments);
  };
})();
window.addEventListener("click", function () { window.__clicks += 1; });
"""


def test_overlapping_renewal_triggers_present_one_renewal_token(rig):
    rig.fake.expires_in = 4  # housekeeping: a renewal is due as soon as the page is signed in
    rig.fake.renewal_gate = threading.Event()  # wl.works holds the first renewal until released
    page = rig.browser_page()
    page.add_init_script(_COUNTS)
    _sign_in(page)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    rig.wait_for(lambda: rig.fake.renewals >= 1)  # the first renewal is at wl.works, held
    page.click(PAUSE)  # under a minute left: the click's `fresh()` renews first
    _until(page, "window.__clicks >= 1")  # the click's handler has run
    asked = page.evaluate("window.__renewals")
    assert asked == 1  # the click joined the renewal in flight and asked for none of its own
    rig.fake.renewal_gate.set()
    rig.wait_for(lambda: _pauses(rig))
    assert rig.fake.renewals == 1
    assert len(rig.fake.presented) == 1  # a count: never the renewal token itself
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)"
    assert _has_signin(page)


#: The page's own sentence once the token has lapsed with wl.works out of reach (the final
#: review, I1).
UNREACHED = "wl.works could not be reached to renew this sign-in; the rig PC's page keeps every control"
#: Counts, in the page, every command it sends to the rig.
_COMMANDS = """
window.__commands = 0;
(function () {
  var real = window.fetch;
  window.fetch = function (url) {
    if (String(url).indexOf("/commands") >= 0) { window.__commands += 1; }
    return real.apply(this, arguments);
  };
})();
"""

#: Counts, in the page, every sign-out it sends to the rig.
_SIGNOUTS = """
window.__signouts = 0;
(function () {
  var real = window.fetch;
  window.fetch = function (url) {
    if (String(url).indexOf("/signout") >= 0) { window.__signouts += 1; }
    return real.apply(this, arguments);
  };
})();
"""


def _signed_out_by_the_page(page) -> bool:
    return (
        page.evaluate("document.body.getAttribute('data-signed-in')") == "0"
        and page.inner_text("#member") == ""
        and page.is_visible("#signin")
        and not _has_signin(page)
    )


def test_an_outage_past_the_tokens_end_signs_the_page_out_on_its_own_and_a_press_sends_nothing(rig, monkeypatch):
    # Spec §7, row 1: the sign-in works until its hour ends, then the page signs out with the
    # reason. None of the rig's minute of leeway, so a lapsed token would be refused there too.
    monkeypatch.setattr(signin, "LEEWAY_S", 0)
    rig.fake.expires_in = 8  # housekeeping: renewed at half of it, tried again at its end
    page = rig.browser_page()
    page.add_init_script(_SIGNOUTS)
    _sign_in(page)
    rig.fake.stop()  # wl.works goes down, and stays down
    # The renewal fails with time left: the sign-in stands, and the page will try again.
    page.wait_for_selector("#sent:has-text('trying again until it lapses')")
    assert page.evaluate("document.body.getAttribute('data-signed-in')") == "1"
    assert _has_signin(page)
    # At the token's end, with no press, the page signs itself out and says why.
    _until(page, "document.body.getAttribute('data-signed-in') === '0'", rig.fake.expires_in + WAIT_S)
    assert _signed_out_by_the_page(page)
    assert page.inner_text("#sent") == "signed out: " + UNREACHED
    signouts = page.evaluate("window.__signouts")  # a lapsed token is never sent to /signout
    assert signouts == 0
    # A press then sends nothing, and the reason stays on the page.
    page.evaluate(_COMMANDS)
    page.click(PAUSE, force=True)  # a click on the greyed button
    page.keyboard.press("p")
    sent = page.evaluate("window.__commands")  # after both presses' handlers have run
    assert sent == 0
    assert len(_pauses(rig)) == 0
    assert page.inner_text("#sent") == "signed out: " + UNREACHED


def test_a_press_after_the_tokens_end_with_wl_works_out_of_reach_says_why_and_sends_nothing(rig):
    # A tab whose timers have not run (a background tab's are held back) is pressed after its
    # token's end: the press finds the lapse itself, and says so instead of "sign in".
    page = rig.browser_page()
    page.clock.install()  # the page's clock is the test's from here, the sign-in's return included
    _sign_in(page)
    rig.fake.stop()  # wl.works goes down
    now = page.evaluate("Date.now()") / 1000
    page.clock.pause_at(now + 1)  # no timer fires after this
    page.clock.set_system_time(now + rig.fake.expires_in + 60)  # past the hour, by the page's clock
    assert page.evaluate("document.body.getAttribute('data-signed-in')") == "1"
    page.evaluate(_COMMANDS)
    page.click(PAUSE)
    page.wait_for_selector("#sent:has-text('not sent:')")
    assert page.inner_text("#sent") == "not sent: " + UNREACHED
    sent = page.evaluate("window.__commands")
    assert sent == 0
    assert len(_pauses(rig)) == 0
    assert _signed_out_by_the_page(page)


def test_a_press_while_the_rig_confirms_a_renewal_waits_for_it_and_is_sent(rig, monkeypatch):
    # Between a renewal's new pair and /whoami's answer the sign-in has no name yet (`keep`),
    # while the controls stay live. A press then was refused with "sign in with wl.works";
    # found when the test below failed on a slow run of the suite. The rig holds its checks
    # here, so the press lands in that window every time.
    checks = threading.Event()
    checks.set()
    real = signin.Checker.check

    def held(self, authorization):
        checks.wait(timeout=20.0)  # bounded: a failing test must not hang its teardown
        return real(self, authorization)

    monkeypatch.setattr(signin.Checker, "check", held)
    rig.fake.expires_in = 4  # housekeeping: a renewal is due as soon as the page is signed in
    page = rig.browser_page()
    page.add_init_script(_COUNTS)
    _sign_in(page)
    page.evaluate("window.__first = JSON.parse(window.sessionStorage.getItem('wlx-signin')).access; 0")
    page.evaluate(_COMMANDS)
    checks.clear()  # the rig holds every check from here
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    # wl.works has renewed, and the rig has not yet confirmed the new token. A bool: never a token.
    _until(page, "JSON.parse(window.sessionStorage.getItem('wlx-signin')).access !== window.__first")
    page.click(PAUSE)
    _until(page, "window.__clicks >= 1")  # the click's handler has run
    told = page.inner_text("#sent")
    assert not told.startswith("not sent")  # the press waits for the renewal, refused by nothing
    # ...and sends nothing until the rig has confirmed the new token: the rig's held check
    # would hold a command too, so the page's own count is what tells the two apart.
    sent = page.evaluate("window.__commands")
    assert sent == 0
    checks.set()

    def paused() -> bool:
        return bool(_pauses(rig))

    rig.wait_for(paused)
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"
    page.wait_for_selector("#sent:has-text('sent: test')")


def test_an_outage_shorter_than_the_token_leaves_the_sign_in_standing(rig, monkeypatch):
    monkeypatch.setattr(signin, "LEEWAY_S", 0)
    rig.fake.expires_in = 8  # housekeeping: renewed at half of it, tried again at its end
    page = rig.browser_page()
    _sign_in(page)
    page.evaluate("window.__first = JSON.parse(window.sessionStorage.getItem('wlx-signin')).access; 0")
    page.route("**/oauth2/token", lambda route: route.abort())  # wl.works out of reach
    page.wait_for_selector("#sent:has-text('trying again until it lapses')")
    page.unroute("**/oauth2/token")  # and back, before the token's end
    renewed = (
        "(function () { var held = JSON.parse(window.sessionStorage.getItem('wlx-signin') || 'null');"
        " return !!held && held.access !== window.__first && document.body.getAttribute('data-signed-in') === '1'"
        " && !document.querySelector('" + PAUSE + "').disabled; })()"
    )
    _until(page, renewed, rig.fake.expires_in + WAIT_S)  # a bool from the page: never the token
    assert rig.fake.renewals == 1  # the retry, on its own: the aborted one never reached wl.works
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)"
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


def test_a_held_reward_stays_held_while_frames_arrive(rig):
    rig.hub.offer(frame(paused_at=1_700_000_030.0))
    rig.dispatch.gate = threading.Event()
    page = rig.browser_page()
    _sign_in(page)
    rig.wait_for(lambda: not page.is_disabled(REWARD))
    page.click(REWARD)
    rig.wait_for(rig.dispatch.entered.is_set)
    # A fragment swap runs `applySignIn` over every sign-in control, the held reward's
    # included: count the swaps the page makes, and offer frames that change something.
    page.evaluate(
        "window.__swaps = 0; new MutationObserver(function (m) { window.__swaps += m.length; })"
        ".observe(document.body, { childList: true, subtree: true, characterData: true })"
    )
    for number in range(3):
        before = page.evaluate("window.__swaps")
        rig.hub.offer(frame(paused_at=1_700_000_030.0, trial_index=41 + number, in_session_seconds=4400.0 + 60 * number))
        rig.wait_for(lambda: page.evaluate("window.__swaps") > before)
        assert page.is_disabled(REWARD)
    assert page.is_disabled(REWARD)
    page.evaluate(f"document.querySelector('{REWARD}').click()")
    page.click(REWARD, force=True)  # a forced click on the held button
    time.sleep(0.5)  # housekeeping: room for a wrong second send to arrive
    assert len(_rewards(rig)) == 1
    rig.dispatch.gate.set()
    rig.wait_for(lambda: page.inner_text("#sent") == "sent: test")
    assert len(_rewards(rig)) == 1


def test_a_reload_with_a_lapsed_token_renews_and_stays_signed_in(rig, monkeypatch):
    # The rig allows a minute past a token's end (`signin.LEEWAY_S`); none here, so a few
    # seconds is a lapse. The page is told the token lasts an hour, as a page whose
    # token ran out sooner than said would be: it asks the rig, which says `expired`.
    monkeypatch.setattr(signin, "LEEWAY_S", 0)
    rig.fake.expires_in = 5  # housekeeping: long enough to outlive the sign-in's own /whoami
    rig.fake.told_expires_in = 3600
    page = rig.browser_page()
    _sign_in(page)
    time.sleep(6)  # housekeeping: past the token's own end
    page.reload()
    page.wait_for_selector(SIGNED_IN)  # the stored name shows before anything is asked
    rig.wait_for(lambda: rig.fake.renewals >= 1)  # the lock is taken first, so not at once
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


def test_a_sign_out_during_a_renewal_stands(rig):
    rig.fake.expires_in = 4
    rig.fake.renewal_gate = threading.Event()
    page = rig.browser_page()
    _sign_in(page)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    rig.wait_for(lambda: rig.fake.renewals >= 1)
    page.click("#signout")
    rig.fake.renewal_gate.set()
    rig.wait_for(lambda: rig.fake.replied >= 1)  # wl.works has answered, late
    page.evaluate("new Promise(function (done) { setTimeout(done, 250); })")  # housekeeping: the page reads it

    def signed_out() -> bool:
        return page.inner_text("#member") == "" and page.is_disabled(PAUSE) and not _has_signin(page)

    assert signed_out()
    time.sleep(1.5)  # housekeeping: nothing may bring the sign-in back later either
    assert signed_out()


def test_a_reload_with_little_time_left_renews_before_asking_the_rig(rig, monkeypatch):
    asked: list = []
    real = signin.Checker.check

    def recording(self, authorization):
        asked.append(authorization)
        return real(self, authorization)

    monkeypatch.setattr(signin.Checker, "check", recording)
    rig.fake.expires_in = 40  # housekeeping: under the 60 s `FRESH_FOR_MS`, over the sign-in's own needs
    page = rig.browser_page()
    _sign_in(page)
    old = "Bearer " + _stored(page)["access"]
    before = len(asked)
    page.reload()
    page.wait_for_selector(SIGNED_IN)
    rig.wait_for(lambda: rig.fake.renewals >= 1)
    rig.wait_for(lambda: len(asked) > before)
    after_reload = asked[before:]
    old_was_sent = any(sent == old for sent in after_reload)  # a bool: never the token
    assert not old_was_sent
    assert len(after_reload) >= 1  # the renewed token was checked


# --- b2b-ready §4.1-§4.4 ----------------------------------------------------------------

#: The page's sentences (b2b-ready §4), as `web._SCRIPT` holds them.
UNCONFIRMED = "this rig has not confirmed the sign-in; trying again"
BUSY = "wl.works could not renew this sign-in just now; trying again until it lapses"


def test_a_renewal_that_hangs_signs_the_page_out_at_the_lapse_and_a_waiting_press_sends_nothing(rig, monkeypatch):
    # XC-229: wl.works takes the renewal and does not answer until the test lets it.
    monkeypatch.setattr(signin, "LEEWAY_S", 0)
    rig.fake.expires_in = 6  # housekeeping: renewed at half of it, so held from about 3 s
    rig.fake.renewal_gate = threading.Event()
    page = rig.browser_page()
    page.add_init_script(_SIGNOUTS)
    _sign_in(page)
    rig.wait_for(lambda: rig.fake.renewals >= 1)  # the renewal is at wl.works, held
    page.evaluate(_COMMANDS)
    page.click(PAUSE)  # under a minute left: the press joins the renewal and waits
    _until(page, "document.body.getAttribute('data-signed-in') === '0'", rig.fake.expires_in + WAIT_S)
    assert _signed_out_by_the_page(page)
    page.wait_for_selector("#sent:has-text('not sent:')")
    assert page.inner_text("#sent") == "not sent: " + UNREACHED
    sent = page.evaluate("window.__commands")
    assert sent == 0
    assert len(_pauses(rig)) == 0
    signouts = page.evaluate("window.__signouts")
    assert signouts == 0
    rig.fake.renewal_gate.set()  # wl.works answers, late
    rig.wait_for(lambda: rig.fake.replied >= 1)
    page.wait_for_timeout(500)  # housekeeping: the page reads the late answer
    assert _signed_out_by_the_page(page)  # dropped: the sign-in stays ended


def test_a_server_error_or_a_body_that_is_not_json_keeps_the_sign_in_and_is_tried_again(rig, monkeypatch):
    # XC-230: only wl.works' own refusal, 400 or 401 with an OAuth error, ends a sign-in.
    monkeypatch.setattr(web, "SIGNIN_RETRY_MS", 500)  # housekeeping: try again soon
    rig.fake.expires_in = 120  # housekeeping: under five minutes, so a wake-up renews
    page = rig.browser_page()
    _sign_in(page)
    page.evaluate("window.__first = JSON.parse(window.sessionStorage.getItem('wlx-signin')).access; 0")
    cors = {"Access-Control-Allow-Origin": rig.origin}
    answers = [
        {"status": 503, "headers": {**cors, "Content-Type": "application/json"},
         "body": '{"error": "temporarily_unavailable"}'},
        {"status": 502, "headers": {**cors, "Content-Type": "text/html"}, "body": "<html>bad gateway</html>"},
        # A 400 without an OAuth `error` is no answer either: only wl.works' own refusal ends it.
        {"status": 400, "headers": {**cors, "Content-Type": "text/html"}, "body": "<html>bad request</html>"},
    ]

    def answer(route) -> None:
        if answers:
            route.fulfill(**answers.pop(0))
        else:
            route.continue_()

    page.route("**/oauth2/token", answer)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_selector("#sent:has-text('could not renew this sign-in just now')")
    assert page.inner_text("#sent") == BUSY
    assert page.evaluate("document.body.getAttribute('data-signed-in')") == "1"
    assert _has_signin(page)
    renewed = (
        "(function () { var held = JSON.parse(window.sessionStorage.getItem('wlx-signin') || 'null');"
        " return !!held && held.access !== window.__first && document.body.getAttribute('data-signed-in') === '1'"
        " && !document.querySelector('" + PAUSE + "').disabled; })()"
    )
    _until(page, renewed)  # a bool from the page: never the token
    assert not answers  # all three were answered before wl.works renewed
    assert rig.fake.renewals == 1  # only the last try reached wl.works
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


def test_a_renewal_the_rig_cannot_confirm_greys_the_controls_and_a_waiting_press_says_so(rig, monkeypatch):
    # XC-231: wl.works renews, and /whoami cannot reach the rig. Ruling 1: one sentence for
    # every confirmation the rig cannot give.
    monkeypatch.setattr(web, "SIGNIN_RETRY_MS", 500)  # housekeeping: ask the rig again soon
    rig.fake.expires_in = 50  # housekeeping: under a minute, so a press renews first
    rig.fake.renewal_gate = threading.Event()
    page = rig.browser_page()
    page.add_init_script(_COUNTS)
    _sign_in(page)
    page.route("**/whoami", lambda route: route.abort())  # the rig, out of the page's reach
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    rig.wait_for(lambda: rig.fake.renewals >= 1)  # held at wl.works
    page.evaluate(_COMMANDS)
    page.click(PAUSE)  # joins the renewal
    _until(page, "window.__clicks >= 1")
    rig.fake.renewal_gate.set()
    page.wait_for_selector("#sent:has-text('not sent:')")
    assert page.inner_text("#sent") == "not sent: " + UNCONFIRMED
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)"  # still signed in
    assert page.is_disabled(PAUSE)
    sent = page.evaluate("window.__commands")
    assert sent == 0
    assert len(_pauses(rig)) == 0
    page.unroute("**/whoami")  # the rig is back: the next try confirms
    rig.wait_for(lambda: not page.is_disabled(PAUSE))
    page.wait_for_timeout(1100)  # housekeeping: past the page's `TOGGLE_HOLD_MS` since the first click
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


def test_the_rigs_expired_with_wl_works_out_of_reach_signs_out_and_never_says_renewed(rig, monkeypatch):
    # XC-231 (b2b-ready §4.4): the rig's word on expiry wins over the page's count.
    monkeypatch.setattr(signin, "LEEWAY_S", 0)
    rig.fake.expires_in = 5
    rig.fake.told_expires_in = 3600  # the page counts an hour; the rig, five seconds
    page = rig.browser_page()
    _sign_in(page)
    time.sleep(6)  # housekeeping: past the token's own end at the rig
    page.route("**/oauth2/token", lambda route: route.abort())  # wl.works out of reach
    page.evaluate(_COMMANDS)
    page.click(PAUSE)
    _until(page, "document.body.getAttribute('data-signed-in') === '0'")
    assert _signed_out_by_the_page(page)
    assert page.inner_text("#sent") == "signed out: " + UNREACHED
    assert len(_pauses(rig)) == 0
    sent = page.evaluate("window.__commands")
    assert sent == 1  # the one the rig refused as expired, never sent again


def test_a_press_while_the_rig_cannot_check_sign_ins_keeps_the_sign_in(rig, monkeypatch):
    # Review Focus 1: the seconds after `wlx serve` restarts, before its keys thread has
    # loaded (b2b-ready §3.2). Refused with that sentence; the sign-in stays.
    page = rig.browser_page()
    _sign_in(page)
    real = signin.Checker.check
    once: list = []

    def no_keys_once(self, authorization):
        if not once:
            once.append(1)
            raise signin.Refused("no_keys", signin.NO_KEYS)
        return real(self, authorization)

    monkeypatch.setattr(signin.Checker, "check", no_keys_once)
    page.click(PAUSE)
    page.wait_for_selector("#sent:has-text('has not reached wl.works')")
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)" and _has_signin(page)
    assert len(_pauses(rig)) == 0
    page.wait_for_timeout(1100)  # housekeeping: past the page's `TOGGLE_HOLD_MS`
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


def test_the_rigs_expired_while_a_renewal_is_held_makes_a_later_press_wait_for_it(rig, monkeypatch):
    # Review fix 1: `expired` acts on the token the rig refused, so a renewal already held at
    # wl.works is joined by the next press, never sent past with the refused token.
    monkeypatch.setattr(signin, "LEEWAY_S", 0)
    rig.fake.expires_in = 5
    rig.fake.told_expires_in = 120  # the page counts two minutes; the rig, five seconds
    page = rig.browser_page()
    _sign_in(page)
    time.sleep(6)  # housekeeping: past the token's own end at the rig
    rig.fake.renewal_gate = threading.Event()
    page.add_init_script(_COUNTS)
    page.evaluate(_COUNTS)
    page.evaluate(_COMMANDS)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")  # under five minutes by its count
    rig.wait_for(lambda: rig.fake.renewals >= 1)  # held at wl.works
    page.click(PAUSE)  # the page counts two minutes: sent, and the rig refuses it as expired
    page.wait_for_selector("#sent:has-text('expired')")
    page.wait_for_timeout(1100)  # housekeeping: past the page's `TOGGLE_HOLD_MS`
    page.click(PAUSE)
    _until(page, "window.__clicks >= 2")
    sent = page.evaluate("window.__commands")
    assert sent == 1  # the second press joined the held renewal and sent nothing
    assert len(_pauses(rig)) == 0
    rig.fake.renewal_gate.set()
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"
    sent = page.evaluate("window.__commands")
    assert sent == 2


# --- b2b-ready §4.5-§4.6 ----------------------------------------------------------------

DUPLICATE = "this sign-in is in use in another tab; use that tab, or sign in again here"


def test_a_duplicated_tab_forgets_its_copy_and_the_first_tab_keeps_working(rig):
    # XC-224: a duplicated tab copies sessionStorage, and with it the renewal token.
    first = rig.browser_page()
    _sign_in(first)
    copied = first.evaluate("window.sessionStorage.getItem('wlx-signin')")  # never asserted on
    second = _Opening(first.context.new_page())  # a tab of the same browser
    second.set_default_timeout(WAIT_S * 1000)
    second.add_init_script(f"window.sessionStorage.setItem('wlx-signin', {json.dumps(copied)});")
    second.add_init_script(_SIGNOUTS)
    second.goto(rig.page_url)
    second.wait_for_selector("#sent:has-text('in use in another tab')")
    assert second.inner_text("#sent") == "signed out: " + DUPLICATE
    assert second.evaluate("document.body.getAttribute('data-signed-in')") == "0"
    signouts = second.evaluate("window.__signouts")  # a copy is never signed out: it would
    assert signouts == 0                             # end the first tab's sign-in too
    first.click(PAUSE)  # the first tab still acts
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"
    # Review Focus 4: the second tab signs in on its own, and both act.
    second.click("#signin")
    second.wait_for_selector(SIGNED_IN)
    assert rig.fake.exchanges == 2
    rig.wait_for(lambda: not second.is_disabled(PAUSE))
    rig.wait_for(lambda: not first.is_disabled(PAUSE))


def test_a_duplicate_is_inert_while_it_waits_for_the_lock_and_never_signs_out_the_original(rig, monkeypatch):
    # The copy shows a signed-in view for the whole wait; a sign-out pressed then must not
    # reach the rig with the copied token, which would end the first tab's sign-in.
    monkeypatch.setattr(web, "SIGNIN_LOCK_WAIT_MS", 3000)  # housekeeping: holds the window open
    first = rig.browser_page()
    _sign_in(first)
    copied = first.evaluate("window.sessionStorage.getItem('wlx-signin')")  # never asserted on
    second = _Opening(first.context.new_page())
    second.set_default_timeout(WAIT_S * 1000)
    second.add_init_script(f"window.sessionStorage.setItem('wlx-signin', {json.dumps(copied)});")
    second.add_init_script(_SIGNOUTS)
    second.goto(rig.page_url)
    second.click("#signout")  # the wait is still running
    second.wait_for_selector("#sent:has-text('signed out')")
    assert second.evaluate("document.body.getAttribute('data-signed-in')") == "0"
    second.wait_for_timeout(3500)  # housekeeping: past the wait, where the lock request gives up
    signouts = second.evaluate("window.__signouts")
    assert signouts == 0
    first.click(PAUSE)  # the first tab's sign-in stands
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


def test_a_duplicate_woken_during_its_wait_never_renews_with_the_originals_token(rig, monkeypatch):
    # A renewal by the copy is a reuse at wl.works, which ends every sign-in of the member.
    monkeypatch.setattr(web, "SIGNIN_LOCK_WAIT_MS", 3000)  # housekeeping: holds the window open
    rig.fake.expires_in = 200  # housekeeping: under RENEW_BEFORE_MS, so a wake-up would renew
    first = rig.browser_page()
    _sign_in(first)
    copied = first.evaluate("window.sessionStorage.getItem('wlx-signin')")  # never asserted on
    second = _Opening(first.context.new_page())
    second.set_default_timeout(WAIT_S * 1000)
    second.add_init_script(f"window.sessionStorage.setItem('wlx-signin', {json.dumps(copied)});")
    second.goto(rig.page_url)
    second.evaluate("document.dispatchEvent(new Event('visibilitychange'))")  # the wait is running
    second.wait_for_selector("#sent:has-text('in use in another tab')")
    assert second.evaluate("document.body.getAttribute('data-signed-in')") == "0"
    renewals = rig.fake.renewals
    assert renewals == 0
    first.click(PAUSE)  # the first tab's sign-in stands
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


def test_a_reload_of_a_signed_in_tab_is_never_taken_for_a_duplicate(rig):
    # Review Focus 5: a reloading tab's old document gives its lock up as it goes.
    page = rig.browser_page()
    _sign_in(page)
    for _ in range(3):
        page.reload()
        page.wait_for_selector(SIGNED_IN)
        rig.wait_for(lambda: not page.is_disabled(PAUSE))
        assert "in use in another tab" not in page.inner_text("#sent")
        assert _has_signin(page)


def test_a_page_made_before_the_rig_had_keys_reloads_into_the_sign_in_once_it_has_them(rig_without_keys, monkeypatch):
    # XC-227 (b2b-ready §4.6).
    rig = rig_without_keys
    monkeypatch.setattr(web, "KEYS_RECHECK_MS", 300)  # housekeeping: ask again soon
    page = rig.browser_page()
    loads = []
    page.on("load", lambda *_: loads.append(1))
    assert page.inner_text("#mode") == "read-only · " + signin.NO_KEYS
    assert page.query_selector("#signin") is None
    page.wait_for_timeout(1000)  # housekeeping: several asks, while the rig still has no keys
    assert page.query_selector("#signin") is None
    assert len(loads) == 0  # asking again is not reloading
    rig.checker.load()  # what the keys thread does once wl.works answers
    page.wait_for_selector("#signin")
    # The sign-in is in the new document before its `load` (it waits on the fonts): Playwright
    # delivers the event only while it is called, so it is waited for, with a deadline (the
    # summary and editor build's Task 3: the flake's second cause, `readyState` "interactive").
    end = time.monotonic() + WAIT_S
    while not loads and time.monotonic() < end:
        page.wait_for_timeout(50)
    assert len(loads) == 1, f"the page reloaded {len(loads)} times into the sign-in, not once"
    _sign_in(page)
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


# --- b2b-ready's final review -----------------------------------------------------------

#: The page's sentence at a lapse the rig never confirmed (b2b-ready §4.1), as `web._SCRIPT`
#: holds it.
NEVER_CONFIRMED = "this rig did not confirm the sign-in before it lapsed; the rig PC's page keeps every control"


def test_a_page_served_without_keys_never_asks_for_a_renewal_and_signs_out_at_the_lapse_with_its_own_sentence(
    rig_without_keys,
):
    # The final review, I1: a page whose `data-token-endpoint` is empty posted the renewal
    # token to its own `/`, and blamed wl.works for the rig's 405. Here a tab signed in before
    # `wlx serve` restarted holds a few seconds of its token: the start-up renews it, a
    # wake-up renews it, and so does the lapse.
    rig = rig_without_keys
    access = rig.issuer.mint(aud=rig.origin, exp_in=5)  # housekeeping: a few seconds, so the lapse comes soon
    page = rig.browser_page()
    grants: list = []
    page.on(
        "request",
        lambda request: grants.append(1) if "grant_type" in (request.post_data or "") else None,
    )
    stored = (
        "{id: 'tab-1', access: " + json.dumps(access) + ", refresh: 'r-1', expires: Date.now() + 5000,"
        " name: 'Jake Westerberg', shown: 'Jake Westerberg (wl.works)'}"
    )  # housekeeping: the page counts the token's own 5 s
    page.add_init_script(f"window.sessionStorage.setItem('wlx-signin', JSON.stringify({stored}));")
    page.goto(rig.page_url)
    assert page.inner_text("#mode") == "read-only · " + signin.NO_KEYS
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(1000)  # housekeeping: room for a wrong renewal to be sent
    assert len(grants) == 0  # a count: never the request, which would carry the renewal token
    assert page.evaluate("document.body.getAttribute('data-signed-in')") == "1"
    assert page.inner_text("#sent") == ""  # kept, with nothing said and nothing tried again
    _until(page, "document.body.getAttribute('data-signed-in') === '0'", 5 + WAIT_S)
    assert page.inner_text("#sent") == "signed out: " + signin.NO_KEYS  # the sentence, not the read-only mark
    assert not _has_signin(page)
    assert len(grants) == 0


def test_a_renewal_the_rig_never_confirms_signs_out_at_the_lapse_saying_so(rig):
    # The final review, M1: wl.works renewed and the rig's /whoami never answered. Spec §4.1
    # names this lapse's reason: the rig did not confirm, not wl.works out of reach.
    rig.fake.expires_in = 6  # housekeeping: the renewed token lapses this long after it is kept
    page = rig.browser_page()
    _sign_in(page)
    held: list = []
    page.route("**/whoami", lambda route: held.append(route))  # kept, never fulfilled
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    _until(page, "document.body.getAttribute('data-signed-in') === '0'", rig.fake.expires_in + WAIT_S)
    assert len(held) == 1  # the renewal's confirmation, held to the end
    assert rig.fake.renewals == 1
    assert page.inner_text("#sent") == "signed out: " + NEVER_CONFIRMED
    assert _signed_out_by_the_page(page)


def test_a_renewal_the_rig_cannot_check_yet_is_asked_again_and_comes_back(rig, monkeypatch):
    # The final review, M2: a renewal's confirmation that lands in a restart's window without
    # keys (b2b-ready §3.2) grays the controls with that sentence, and is asked again every
    # RETRY_MS, not left grayed until the lapse.
    monkeypatch.setattr(web, "SIGNIN_RETRY_MS", 2000)  # housekeeping: ask the rig again soon
    rig.fake.expires_in = 120  # housekeeping: under five minutes, so a wake-up renews
    page = rig.browser_page()
    _sign_in(page)
    real = signin.Checker.check
    once: list = []

    def no_keys_once(self, authorization):
        if not once:
            once.append(1)
            raise signin.Refused("no_keys", signin.NO_KEYS)
        return real(self, authorization)

    monkeypatch.setattr(signin.Checker, "check", no_keys_once)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    grayed = (
        "document.querySelector('" + PAUSE + "').disabled && document.getElementById('sent').textContent === "
        + json.dumps("signed in, but not usable now: " + signin.NO_KEYS)
    )
    _until(page, grayed)
    assert rig.fake.renewals == 1
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)" and _has_signin(page)

    def confirmed_again() -> bool:
        return not page.is_disabled(PAUSE)

    rig.wait_for(confirmed_again)
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


#: Counts, in the page, every /whoami the rig answers `signed_in`: the page's own reading of
#: the answer runs beside this one, on a copy of the response.
_CONFIRMS = """
window.__confirms = 0;
(function () {
  var real = window.fetch;
  window.fetch = function (url) {
    var sent = real.apply(this, arguments);
    if (String(url).indexOf("/whoami") >= 0) {
      sent.then(function (response) { return response.clone().json(); }).then(function (answer) {
        if (answer && answer.status === "signed_in") { window.__confirms += 1; }
      }, function () {});
    }
    return sent;
  };
})();
"""


def _held(page, held: list) -> None:
    """Wait until a route has held a request, letting Playwright run its handler meanwhile."""
    end = time.monotonic() + WAIT_S
    while not held:
        if time.monotonic() >= end:
            pytest.fail(f"timed out after {WAIT_S:g} s waiting for a held request")
        page.wait_for_timeout(50)  # housekeeping: lets Playwright run the route's handler meanwhile


def test_the_rigs_expired_for_a_token_already_renewed_neither_renews_again_nor_signs_out(rig, monkeypatch):
    # `expiredAtTheRig`'s guard (the Task 3 review's case c): the rig answers `expired` for a
    # command sent with the old token after a renewal has replaced it. That answer is about a
    # token the page no longer holds, and the renewal token it holds now is not spent on it.
    monkeypatch.setattr(signin, "LEEWAY_S", 0)
    rig.fake.expires_in = 5  # housekeeping: the token's own end at the rig, passed below
    rig.fake.told_expires_in = 120  # the page counts two minutes; the rig, five seconds
    page = rig.browser_page()
    _sign_in(page)
    time.sleep(6)  # housekeeping: past the token's own end at the rig
    page.evaluate("window.__first = JSON.parse(window.sessionStorage.getItem('wlx-signin')).access; 0")
    page.evaluate(_CONFIRMS)
    held: list = []
    page.route("**/commands", lambda route: held.append(route))  # kept until the renewal is done
    page.click(PAUSE)  # the page counts time left: sent with the old token, and held on the way
    _held(page, held)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")  # under five minutes by its count
    renewed = (
        "window.__confirms >= 1 && JSON.parse(window.sessionStorage.getItem('wlx-signin')).access"
        " !== window.__first"
    )
    _until(page, renewed)  # a bool from the page: never the token
    page.wait_for_timeout(300)  # housekeeping: the page finishes the renewal the rig confirmed
    held[0].continue_()  # the rig refuses the old token as expired
    page.wait_for_selector("#sent:has-text('this sign-in was renewed')")
    page.wait_for_timeout(500)  # housekeeping: room for a wrong second renewal to arrive
    assert rig.fake.renewals == 1
    assert page.evaluate("document.body.getAttribute('data-signed-in')") == "1"
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)" and _has_signin(page)


#: Keeps a sign-in in a tab's first document only, numbers each document, and records in
#: sessionStorage whether the pause button was ever live in each, so the record outlives a
#: reload. `%s` is the stored sign-in, as a JavaScript object.
_LIVE_BY_DOCUMENT = """
(function () {
  var number = Number(window.sessionStorage.getItem('test-documents') || '0') + 1;
  window.sessionStorage.setItem('test-documents', String(number));
  if (number === 1) { window.sessionStorage.setItem('wlx-signin', JSON.stringify(%s)); }
  new MutationObserver(function () {
    var pause = document.querySelector('[data-cmd="pause"]');
    if (pause && !pause.disabled) { window.sessionStorage.setItem('test-live-in-' + number, '1'); }
  }).observe(document, { attributes: true, childList: true, subtree: true });
})();
"""


def test_a_page_without_keys_keeps_a_stored_sign_in_grayed_until_its_reload(rig_without_keys, monkeypatch):
    # The fix wave's re-review, Minor 1: on a page without keys, a confirmation retry could
    # confirm a stored sign-in once the rig had keys and make the controls live, and §4.6's
    # reload could then cut off a press in flight. Such a page waits for the reload instead.
    rig = rig_without_keys
    monkeypatch.setattr(web, "KEYS_RECHECK_MS", 5000)  # housekeeping: the §4.6 reload comes late,
    monkeypatch.setattr(web, "SIGNIN_RETRY_MS", 300)  # housekeeping: and a retry, were there one, early
    access = rig.issuer.mint(aud=rig.origin, exp_in=120)  # housekeeping: over a minute, so it is asked about
    page = rig.browser_page()
    stored = (
        "{id: 'tab-1', access: " + json.dumps(access) + ", refresh: 'r-1',"
        " expires: Date.now() + 120000, name: 'Jake Westerberg', shown: 'Jake Westerberg (wl.works)'}"
    )  # housekeeping: the page counts the token's own 120 s
    page.add_init_script(_LIVE_BY_DOCUMENT % stored)
    page.goto(rig.page_url)
    loads = []
    page.on("load", lambda *_: loads.append(1))
    grayed = (
        "document.querySelector('" + PAUSE + "').disabled && document.getElementById('sent').textContent === "
        + json.dumps("signed in, but not usable now: " + signin.NO_KEYS)
    )
    _until(page, grayed)  # the rig cannot check the stored sign-in yet
    rig.checker.load()  # what the keys thread does once wl.works answers

    def reloaded_and_live() -> bool:
        return not page.is_disabled(PAUSE) and bool(loads)  # Playwright first: it delivers `load`

    rig.wait_for(reloaded_and_live)
    assert len(loads) == 1
    live_before_the_reload = page.evaluate("window.sessionStorage.getItem('test-live-in-1') !== null")
    assert not live_before_the_reload
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert _pauses(rig)[-1].by.name == "Jake Westerberg"


def test_a_member_opens_a_session_for_a_kind_and_accepts_the_warning_the_dialog_offers(rig):
    """Test the path, not the piece (ledger D8): the dialog's open, end to end through the
    page's own script and `_command_from`. The rig's dispatch is a stand-in (there is no
    `taskd` behind this page, so no `warnings.jsonl` to read), so what is checked is the
    request that reached it: the kind chosen, and the warning with its sentence, signed by
    the member. **The default calibration's own sentence** (the engine B final review): its
    "²", "§" and "'" go page, serve and `_command_from` and arrive as the `Entry.key` an open is
    held to, character for character."""
    (default,) = warnlist.of_calibration(SRGB, date.today())
    assert {"²", "§", "'"} <= set(default.detail), "the sentence must hold what this tests"
    page = rig.browser_page()
    _sign_in(page)
    rig.hub.offer(idle(warnings=(
        WarningRow.of(default.code, default.detail, default.accepted_in, None, None),
    )))
    page.wait_for_selector('#dn-warnings [data-warn="default calibration"]', state="attached")
    page.click('[data-cmd="new"]')
    page.select_option("#dn-subject", "A")
    page.select_option("#dn-deployment", "rig_fixed")
    page.select_option("#dn-kind", "training")
    page.fill("#dn-id", "s-1")
    page.fill("#dn-left", "07:30")
    page.check("#dn-accept")
    page.click("#dn-ok")
    rig.wait_for(lambda: any(isinstance(seen, OpenSession) for seen in rig.dispatch.seen))
    opened = next(seen for seen in rig.dispatch.seen if isinstance(seen, OpenSession))
    assert opened.session_kind == "training"
    assert opened.by.name == "Jake Westerberg"
    assert opened.accepted == (default.key,)


def _opens(rig) -> list:
    return [seen for seen in rig.dispatch.seen if isinstance(seen, OpenSession)]


def _fill_open(page) -> None:
    page.click('[data-cmd="new"]')
    page.select_option("#dn-subject", "A")
    page.select_option("#dn-deployment", "rig_fixed")
    page.select_option("#dn-kind", "training")
    page.fill("#dn-id", "s-1")
    page.fill("#dn-left", "07:30")


def test_an_open_with_no_deployment_chosen_is_refused_at_the_form(rig):
    """WEL-06 (XC-355): the form starts with no deployment, and an open without one is
    refused where it is typed -- nothing reaches the rig."""
    page = rig.browser_page()
    _sign_in(page)
    rig.hub.offer(idle())
    page.wait_for_selector('#dn-warnings [data-warn="default calibration"]', state="attached")
    _fill_open(page)
    page.select_option("#dn-deployment", "")
    assert page.input_value("#dn-deployment") == ""
    page.click("#dn-ok")
    page.locator("#dn-msg", has_text="a deployment must be chosen").wait_for(state="attached")
    time.sleep(0.3)
    assert _opens(rig) == []


def test_an_open_with_the_accept_box_unticked_accepts_nothing(rig):
    page = rig.browser_page()
    _sign_in(page)
    rig.hub.offer(idle())
    page.wait_for_selector('#dn-warnings [data-warn="default calibration"]', state="attached")
    _fill_open(page)
    assert not page.is_checked("#dn-accept")
    page.click("#dn-ok")
    rig.wait_for(lambda: _opens(rig))
    assert _opens(rig)[0].accepted == ()


def test_the_new_session_dialog_scrolls_to_its_button_in_a_short_window(rig):
    page = rig.browser_page()
    page.set_viewport_size({"width": 800, "height": 500})
    _sign_in(page)
    head_free = WarningRow(
        HEAD_FREE, "a chaired session leaves the head free to move: " + "words " * 60, SESSION_KINDS, None, None
    )
    rig.hub.offer(idle(warnings=idle().warnings + (head_free,)))
    page.wait_for_selector(f'#dn-warnings [data-warn="{HEAD_FREE}"]', state="attached")
    _fill_open(page)
    taller = page.evaluate('document.querySelector("#dlg-new .dialog").getBoundingClientRect().height > 500')
    assert taller, "the dialog must be taller than the window for this to test scrolling"
    page.click("#dn-ok")  # Playwright scrolls the button into view first
    rig.wait_for(lambda: _opens(rig))


# --- Plans (engine build C2b) ----------------------------------------------------------------


def _between_runs(**over):
    """A `wlx taskd` session between runs offering a task with plans, its first run ended."""
    fields = dict(phase="between_runs", service=True, run_index=0, stop_kind="completed",
                  stopped_because="every block is finished",
                  offered_tasks=("fixation_detection.py", "planned.py"))
    fields.update(over)
    return frame(**fields)


def _checks(rig) -> list:
    return [seen for seen in rig.dispatch.seen if isinstance(seen, CheckRun)]


def test_choosing_a_task_preselects_its_first_plan_and_start_sends_the_plan_its_preflight_is_for(
        rig):
    """The PI, 2026-10-19, "Preselect first, keep plain": choosing a task takes its pre-flight,
    and once that brings the task's plans the page preselects the first, takes the pre-flight for
    it and hides the plain run's trials box; *start run* then sends that plan, as the member's.
    Test the path through the page's own script: the select, the frame, the swap, the post."""
    rig.hub.offer(_between_runs())
    page = rig.browser_page()
    _sign_in(page)
    page.select_option("#task-sel", "planned.py")
    rig.wait_for(lambda: _checks(rig))
    passing = (PreflightItem("task checks", "pass", "planned.py passes its load-time checks"),)
    rig.hub.offer(_between_runs(preflight=Preflight("planned.py", passing, plan=None,
                                                    plans=("train", "test"))))
    rig.wait_for(lambda: len(_checks(rig)) == 2)
    rig.hub.offer(_between_runs(preflight=Preflight("planned.py", passing, plan="train",
                                                    plans=("train", "test"))))
    page.wait_for_selector('[data-cmd="start"][data-plan="train"]:not([disabled])')
    hidden = page.evaluate('document.getElementById("run-trials").closest("label").hidden')
    page.click('[data-cmd="start"]')
    rig.wait_for(lambda: any(isinstance(seen, StartRun) for seen in rig.dispatch.seen))

    first, second = _checks(rig)
    started = next(seen for seen in rig.dispatch.seen if isinstance(seen, StartRun))
    assert (first.task, first.plan, second.task, second.plan) == (
        "planned.py", None, "planned.py", "train")
    assert hidden is True
    assert (started.task, started.plan, started.by.name) == (
        "planned.py", "train", "Jake Westerberg")


def test_the_only_task_offered_has_its_first_plan_preselected_as_its_plans_arrive(rig):
    """The engineering review, I3: on a rig offering one task, the task selector never changes, so
    the page preselected nothing. Its plans arrive with the pre-flight the pill takes, and the
    first is preselected then and its pre-flight taken -- once: the plan's own pre-flight leaves
    it standing."""
    rig.hub.offer(_between_runs(offered_tasks=("planned.py",)))
    page = rig.browser_page()
    _sign_in(page)
    page.click('[data-cmd="check"]')
    rig.wait_for(lambda: _checks(rig))
    passing = (PreflightItem("task checks", "pass", "planned.py passes its load-time checks"),)
    rig.hub.offer(_between_runs(offered_tasks=("planned.py",), preflight=Preflight(
        "planned.py", passing, plan=None, plans=("train", "test"))))
    rig.wait_for(lambda: len(_checks(rig)) == 2)
    rig.hub.offer(_between_runs(offered_tasks=("planned.py",), preflight=Preflight(
        "planned.py", passing, plan="train", plans=("train", "test"))))
    page.wait_for_selector('[data-cmd="start"][data-plan="train"]:not([disabled])')

    assert page.evaluate('document.getElementById("plan-sel").value') == "train"
    assert [(check.task, check.plan) for check in _checks(rig)] == [
        ("planned.py", None), ("planned.py", "train")]


def test_next_block_and_back_one_reach_the_rig_as_the_members(rig):
    """The PI, 2026-10-19, "'Next' and 'back one'": "Both directions by hand, each recorded with
    who"."""
    rig.hub.offer(frame(plan="train", block="easy", next_block="hard"))
    page = rig.browser_page()
    _sign_in(page)

    page.click('[data-cmd="next_block"]')
    rig.wait_for(lambda: rig.dispatch.seen)
    page.click('[data-cmd="back_block"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)

    moved, back = rig.dispatch.seen
    assert (type(moved), moved.by.name) == (NextBlock, "Jake Westerberg")
    assert (type(back), back.by.name) == (BackBlock, "Jake Westerberg")


def test_the_page_shows_a_settings_position_eccentricity_and_direction_first(rig):
    """XC-401 (the PI, 2026-10-19, "Polar first, x-y allowed"): a setting holding the per-axis
    position (20°, 20°) is shown on its card as the rig made it, eccentricity and direction first
    -- 27.236° out at 45°, the true visual angle, never the 28.284° `√(x² + y²)` gives -- with its
    (x, y) beside them, and no input to set it. Through the wire, in a real browser."""
    from wl_xcon.link import ParamRow, decode, encode

    row = ParamRow.of("target_pos", "deg", None, None, (20.0, 20.0), False,
                      ((20.0, 20.0), (0.0, 10.0)))
    held = ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False)
    rig.hub.offer(decode(encode(frame(params=(row, held)))))
    page = rig.browser_page()

    page.locator("#params", has_text="27.236° at 45°").wait_for(state="attached")
    card = page.locator("#params .box").first
    text = card.text_content()

    assert "target_pos" in text and "27.236° at 45° · (x, y) (20, 20)" in text
    assert text.index("27.236°") < text.index("(x, y)") and "28.28" not in text
    assert card.locator("input").count() == 0
    assert page.locator('#params input[data-param="fix_hold"]').count() == 1


def test_the_page_keeps_its_controls_while_a_setting_holds_no_number_or_word(rig):
    """XC-401's second fix round: a setting holding a value that is neither a number nor a word --
    here a pair held by a setting not declared a position -- made its card raise, and `serve`
    builds the page and its event stream unguarded, so the page went blank and the operator lost
    pause, mark, reward and stop for as long as the value stood. The card shows the value as
    written, with no input, and every control stays. Through the wire, in a real browser."""
    from wl_xcon.link import ParamRow, decode, encode

    span = ParamRow.of("span", "deg", 0.0, 1.0, (0.3, 0.6), False, ())
    rig.hub.offer(decode(encode(frame(params=(span,)))))
    page = rig.browser_page()

    page.locator("#params", has_text="[0.3, 0.6]").wait_for(state="attached")

    assert page.locator("#params .box").count() == 1
    assert page.locator("#params .box").first.locator("input").count() == 0
    for command in ("pause", "mark", "reward", "stop"):
        assert page.locator(f'#controls [data-cmd="{command}"]').count() == 1, command


ONE_TASK = ("planned.py",)
PASSING = (PreflightItem("task checks", "pass", "planned.py passes its load-time checks"),)


def _plans_of(taken, plans=("train", "test"), **over):
    """A between-runs frame offering the one task with plans, its pre-flight taken for `taken`."""
    return _between_runs(offered_tasks=ONE_TASK, preflight=Preflight(
        "planned.py", PASSING, plan=taken, plans=plans), **over)


def _second_run_pill(rig, page, last, plans, *, task="tasks/planned.py"):
    """A first run of `last` has ended: the frame between runs carries it, as taskd's does, the
    pill is pressed and the plain pre-flight's `plans` arrive."""
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK, run_index=1, plan=last, block="easy",
                                task=task))
    page.wait_for_selector('[data-cmd="check"]:not([disabled])')
    before = len(_checks(rig))
    page.click('[data-cmd="check"]')
    rig.wait_for(lambda: len(_checks(rig)) == before + 1)
    rig.hub.offer(_plans_of(None, plans, run_index=1, plan=last, task=task))
    page.locator("#plan-sel option").nth(1).wait_for(state="attached")


#: A banner text no other frame says, to see that a frame was swapped in.
FRAME_MARKER = "frame-marker-7f3"


def _marker_shown(page, timeout_ms: float = WAIT_S * 1000) -> None:
    """Wait for `FRAME_MARKER` in the banners. A locator, not `wait_for_function`: that polls by
    evaluating a string in the page, which the page's Content-Security-Policy refuses, and only
    a condition already true at its first look got through (CI, Python 3.11 and 3.12)."""
    page.locator("#banners", has_text=FRAME_MARKER).wait_for(state="attached", timeout=timeout_ms)


def _after_a_frame_is_processed(rig, page, *, late_s: float = 0.0):
    """Wait until the page has swapped in a frame offered after it loaded (offered `late_s`
    seconds from now, to see the wait poll). `preselect` runs inside that synchronous swap and
    sets `#plan-sel` before it posts anything, so what the page would have sent on a frame is
    sent, or not, by the time this returns; no fixed wait."""
    offer = lambda: rig.hub.offer(_plans_of(None, stopped_because=FRAME_MARKER))  # noqa: E731
    late = threading.Timer(late_s, offer) if late_s else None
    if late:
        late.start()
    else:
        offer()
    try:
        _marker_shown(page)
    finally:
        if late:
            late.cancel()


def test_the_wait_for_a_frame_polls_when_the_frame_comes_late_and_fails_plainly_when_not(rig):
    """CI: the marker wait must work when it has to poll, which the page's Content-Security-Policy
    allows only for a locator; and a page that never gets the frame fails at the locator's
    timeout, naming what it waited for, not with an EvalError."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    rig.hub.offer(_plans_of(None))
    page = rig.browser_page()
    _after_a_frame_is_processed(rig, page, late_s=1.5)

    with pytest.raises(PlaywrightTimeoutError) as raised:
        page.locator("#banners", has_text="never-offered").wait_for(
            state="attached", timeout=500)
    assert "Timeout 500ms exceeded" in str(raised.value) and "never-offered" in str(raised.value)


def _preselected(rig, page):
    """The one-task rig's first run offered: the pill's plain pre-flight, its plans arriving, the
    first preselected and its pre-flight taken."""
    page.click('[data-cmd="check"]')
    rig.wait_for(lambda: len(_checks(rig)) == 1)
    rig.hub.offer(_plans_of(None))
    rig.wait_for(lambda: len(_checks(rig)) == 2)
    rig.hub.offer(_plans_of("train"))
    page.wait_for_selector('[data-cmd="start"][data-plan="train"]:not([disabled])')


def test_a_later_run_on_a_one_task_rig_preselects_the_first_plan_again(rig):
    """The task's first review, I1a: taskd clears the pre-flight at run start, so the next run's
    plans came back to a page that had "already" offered them, and nothing was preselected. A run
    is a plan's while it runs -- the bar shows that plan, the Trials box hidden -- and the next
    run's plain pre-flight, on the pill, preselects the plan last run (the PI, 2026-10-22, "The
    plan last run"), here the task's second, so "last" is told from "first"; the session's first
    run preselected the task's first (Q9)."""
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    page = rig.browser_page()
    _sign_in(page)
    _preselected(rig, page)
    page.select_option("#plan-sel", "test")
    rig.wait_for(lambda: len(_checks(rig)) == 3)

    rig.hub.offer(frame(plan="test", block="easy", next_block="hard", offered_tasks=ONE_TASK,
                        task="tasks/planned.py", preflight=None))
    page.wait_for_selector('[data-cmd="next_block"]', state="attached")
    during = page.evaluate('[document.getElementById("plan-sel").value, '
                           'document.getElementById("run-trials").closest("label").hidden]')
    # As taskd sends it: between runs the frame still carries the last run's plan.
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK, run_index=1, plan="test", block="easy",
                                task="tasks/planned.py"))
    page.wait_for_selector('[data-cmd="next_block"]', state="detached")
    plain_between = page.evaluate('document.getElementById("plan-sel").value')
    page.click('[data-cmd="check"]')
    rig.wait_for(lambda: len(_checks(rig)) == 4)
    rig.hub.offer(_plans_of(None, run_index=1, plan="test", task="tasks/planned.py"))
    rig.wait_for(lambda: len(_checks(rig)) == 5)

    assert during == ["test", True] and plain_between == ""
    assert [(check.task, check.plan) for check in _checks(rig)] == [
        ("planned.py", None), ("planned.py", "train"), ("planned.py", "test"),
        ("planned.py", None), ("planned.py", "test")]
    assert page.evaluate('document.getElementById("plan-sel").value') == "test"


def test_a_plain_last_run_is_repeated_as_the_plain_run_but_the_first_run_gets_the_first_plan(rig):
    """The PI, 2026-10-22, "The plan last run" -- "Repeats what the operator just ran": a session
    whose last run of this task was the plain run keeps the plain run for the next, the first plan
    being only for the session's first run (Q9; `_preselected` is that first run)."""
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    page = rig.browser_page()
    _sign_in(page)
    _preselected(rig, page)
    page.select_option("#plan-sel", "")
    rig.wait_for(lambda: len(_checks(rig)) == 3)

    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK, run_index=1, plan=None,
                                task="tasks/planned.py"))
    page.wait_for_selector('[data-cmd="check"]:not([disabled])')
    page.click('[data-cmd="check"]')
    rig.wait_for(lambda: len(_checks(rig)) == 4)
    again = dict(run_index=1, plan=None, task="tasks/planned.py")
    rig.hub.offer(_plans_of(None, **again))
    rig.hub.offer(_plans_of(None, stopped_because=FRAME_MARKER, **again))
    _marker_shown(page)

    assert [(check.task, check.plan) for check in _checks(rig)] == [
        ("planned.py", None), ("planned.py", "train"), ("planned.py", None),
        ("planned.py", None)]
    assert page.evaluate('document.getElementById("plan-sel").value') == ""


def test_a_last_plan_no_longer_among_the_tasks_plans_falls_back_to_its_first(rig):
    """The PI, 2026-10-22: the plan last run is preselected "if it is still among the task's
    plans"; the task was edited between the runs, so the first is."""
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    page = rig.browser_page()
    _sign_in(page)
    _second_run_pill(rig, page, "test", ("alpha", "beta"))
    rig.wait_for(lambda: len(_checks(rig)) == 2)

    assert [(check.task, check.plan) for check in _checks(rig)] == [
        ("planned.py", None), ("planned.py", "alpha")]
    assert page.evaluate('document.getElementById("plan-sel").value') == "alpha"


def test_another_task_chosen_after_a_run_gets_its_own_first_plan(rig):
    """The PI, 2026-10-22: the plan last run is the same task's. The operator switches to another
    task whose plans include a plan of the same name: its first is preselected, not that one."""
    rig.hub.offer(_between_runs(offered_tasks=("planned.py", "other.py"), run_index=1,
                                plan="test", block="easy", task="tasks/planned.py"))
    page = rig.browser_page()
    _sign_in(page)
    page.select_option("#task-sel", "other.py")
    rig.wait_for(lambda: _checks(rig))
    rig.hub.offer(_between_runs(
        offered_tasks=("planned.py", "other.py"), run_index=1, plan="test", block="easy",
        task="tasks/planned.py", preflight=Preflight(
            "other.py", PASSING, plan=None, plans=("alpha", "test"))))
    rig.wait_for(lambda: len(_checks(rig)) == 2)

    assert [(check.task, check.plan) for check in _checks(rig)] == [
        ("other.py", None), ("other.py", "alpha")]
    assert page.evaluate('document.getElementById("plan-sel").value') == "alpha"


def test_a_reload_after_an_explicit_plain_choice_keeps_the_plain_run(rig):
    """The task's first review, I1b: the plain run, chosen by a person, stood only until the page
    was reloaded, when it preselected the first plan again and took its pre-flight. Only a
    pre-flight this page asked for arms the preselection."""
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    page = rig.browser_page()
    _sign_in(page)
    _preselected(rig, page)
    page.select_option("#plan-sel", "")
    rig.wait_for(lambda: len(_checks(rig)) == 3)
    rig.hub.offer(_plans_of(None))
    page.wait_for_selector('[data-cmd="start"][data-plan=""]:not([disabled])')

    page.reload()
    _after_a_frame_is_processed(rig, page)

    assert len(_checks(rig)) == 3
    assert page.evaluate('document.getElementById("plan-sel").value') == ""


def test_a_page_not_signed_in_sends_and_says_nothing_as_it_loads(rig):
    """The task's first review, I1c: a page with no one signed in preselected a task's plan on
    load and said "not sent: sign in". Opening a page asks for nothing."""
    rig.hub.offer(_plans_of(None))
    page = rig.browser_page()
    _after_a_frame_is_processed(rig, page)

    assert _checks(rig) == []
    assert page.evaluate('document.getElementById("sent").textContent.trim()') == ""
    # Nor is a plan preselected on a page that cannot send (the final review, T10).
    assert page.evaluate('document.getElementById("plan-sel").value') == ""


def test_a_double_click_on_next_block_or_back_one_is_one_move(rig):
    """The task's first review, I2: pause, reward and clear are held against a double click; the
    moves between blocks are too. A second, different move is the synchronization: it arrives
    after the first double click's second click would have."""
    rig.hub.offer(frame(plan="train", block="easy", next_block="hard"))
    page = rig.browser_page()
    _sign_in(page)

    page.dblclick('[data-cmd="next_block"]')
    rig.wait_for(lambda: rig.dispatch.seen)
    page.dblclick('[data-cmd="back_block"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) >= 2)
    page.wait_for_timeout(800)

    assert [type(seen) for seen in rig.dispatch.seen] == [NextBlock, BackBlock]


def test_a_plan_start_ignores_the_hidden_trials_box(rig):
    """The task's first review, M4: the Trials box is hidden while a plan is chosen, so a bad value
    left in it must not refuse a plan's start and point at a box the person cannot see."""
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    page = rig.browser_page()
    _sign_in(page)
    _preselected(rig, page)

    page.evaluate('document.getElementById("run-trials").value = "many"')
    page.click('[data-cmd="start"]')
    rig.wait_for(lambda: any(isinstance(seen, StartRun) for seen in rig.dispatch.seen))

    started = next(seen for seen in rig.dispatch.seen if isinstance(seen, StartRun))
    assert (started.task, started.plan) == ("planned.py", "train")


def test_the_run_start_shows_yesterdays_end_and_sends_the_stage_level_and_pairings_picked(rig):
    """The pop-out search build's Task 6 (its design §3.5, the PI's sketch: "at the day's start,
    the stage, the staircase's starting level and the pairings to pick, with yesterday's end
    shown"): the Setup tab shows the previous session's end and offers the plan's stages, the
    picked stage's staircase level and the pool's pairings; picks survive a frame redrawing the
    pre-flight, and *start run* sends the stage picked and, as the start's values, only what the
    person changed from where the run would start."""
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    page = rig.browser_page()
    _sign_in(page)
    _preselected(rig, page)
    previous = ("session 2027-01-13_01's last run of plan train ended in Crowd; set_size at 8, by "
                "its staircase; pairings 5 (blue>red, red>blue)")
    starting = Preflight(
        "planned.py", PASSING, plan="train", plans=("train", "test"),
        stages=(StageRow("Alone"), StageRow("Crowd", "set_size", (4, 6, 8, 10), 1, False)),
        pool=PoolRow("pairings", ("blue>red", "purple>red", "red>blue"), 1), previous=previous)
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK, preflight=starting))
    page.click('label[for="t-setup"]')
    page.wait_for_selector("#start-block")

    shown = page.inner_text("#previous-end")
    crowd_hidden = page.evaluate(
        'document.querySelector(\'#run-start [data-stage="Crowd"]\').hidden')
    def starts() -> list:
        return [seen for seen in rig.dispatch.seen if isinstance(seen, StartRun)]

    # A start with nothing picked sends nothing: the run starts where it would.
    page.click('[data-cmd="start"]')
    rig.wait_for(lambda: len(starts()) == 1)
    # A stage picked, its level and the pairings left as they would start: only the stage.
    page.select_option("#start-block", "Crowd")
    page.click('[data-cmd="start"]')
    rig.wait_for(lambda: len(starts()) == 2)
    page.select_option("#start-block", "Crowd")
    page.select_option('select[data-start-setting="set_size"]', "8")
    page.check('input[data-pairing="2"]')
    # A frame redrawing the pre-flight, as a pre-flight taken again does: the page swaps only a
    # pane that changed.
    again = (PreflightItem("task checks", "pass", "planned.py passes its load-time checks again"),)
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK, preflight=dataclasses.replace(
        starting, items=again), stopped_because=FRAME_MARKER))
    _marker_shown(page)
    page.click('[data-cmd="start"]')
    rig.wait_for(lambda: len(starts()) == 3)

    plain, staged, picked = starts()
    assert previous in shown and crowd_hidden is True
    assert (plain.plan, plain.start_block, plain.values) == ("train", None, {})
    assert (staged.start_block, staged.values) == ("Crowd", {})
    assert (picked.plan, picked.start_block, picked.values) == (
        "train", "Crowd", {"set_size": 8, "pairings": 3})


def test_the_preflight_check_sends_the_stage_picked_and_keeps_the_picks(rig):
    """The pop-out search build's Task 7: the stage picked is sent with the pre-flight's check, not
    only with the start, so its task checks judge a start there before the trainer starts: picking a
    stage takes the pre-flight again at it, and so does the pill, for the task and plan it shows;
    the picks outlive it, the rig's answer redrawing the pre-flight included, and the first stage
    sends none."""
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    page = rig.browser_page()
    _sign_in(page)
    _preselected(rig, page)
    starting = Preflight(
        "planned.py", PASSING, plan="train", plans=("train", "test"),
        stages=(StageRow("Alone"), StageRow("Crowd", "set_size", (4, 6, 8, 10), 1, False)),
        pool=PoolRow("pairings", ("blue>red", "purple>red", "red>blue"), 1))
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK, preflight=starting))
    page.click('label[for="t-setup"]')
    page.wait_for_selector("#start-block")
    before = len(_checks(rig))

    page.check('input[data-pairing="2"]')
    page.select_option("#start-block", "Crowd")
    rig.wait_for(lambda: len(_checks(rig)) == before + 1)
    # The rig answers with the pre-flight taken at Crowd, which redraws the pane.
    again = (PreflightItem("task checks", "pass", "planned.py starts at Crowd"),)
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK, stopped_because=FRAME_MARKER,
                                preflight=dataclasses.replace(starting, items=again,
                                                              start_block="Crowd")))
    _marker_shown(page)
    page.locator("#preflight", has_text="planned.py starts at Crowd").wait_for()
    kept = page.is_checked('input[data-pairing="2"]')
    page.click('[data-cmd="check"]')
    rig.wait_for(lambda: len(_checks(rig)) == before + 2)
    page.select_option("#start-block", "Alone")
    rig.wait_for(lambda: len(_checks(rig)) == before + 3)
    page.click('[data-cmd="start"]')
    rig.wait_for(lambda: any(isinstance(seen, StartRun) for seen in rig.dispatch.seen))

    picked, again, first = _checks(rig)[before:]
    (start,) = [seen for seen in rig.dispatch.seen if isinstance(seen, StartRun)]
    assert (picked.task, picked.plan, picked.start_block) == ("planned.py", "train", "Crowd")
    assert (again.plan, again.start_block) == ("train", "Crowd")
    assert (first.plan, first.start_block) == ("train", None)
    assert kept is True
    assert (start.start_block, start.values) == (None, {"pairings": 3})


#: The trainer's panel's run (the pop-out search build's Task 7): a confirmed progression in
#: Fade-in, its staircase on the distractors' luminance, two of four pairings pooled, the bar to
#: move up met and the pool's widening with it, one prompt.
_UP = Suggestion(7, "up", "Fade-in", "Crowd", 41, 50, True)
_WIDEN = Suggestion(8, "widen", "Fade-in", None, 41, 50, True)
_TRAINING = dict(
    plan="train", block="Fade-in", next_block="Crowd",
    staircase=StaircaseRow("distractor_luminance", (0.25, 0.5, 0.75, 1.0), 2, False, 3, 1),
    pool=Pooled("pairings", ("blue>red", "red>blue", "purple>red", "red>purple"), 5),
    suggestion=_UP, widen=_WIDEN)


def test_a_suggestion_is_answered_from_the_trainers_panel(rig):
    """The pop-out search build's Task 7 (its design §3.5; the PI's sketch of the trainer's screen):
    *Move up* sends `next_block` naming the suggestion it confirms and *Hold* `decline` naming it;
    *lock at* holds the staircase's setting at its level, a person's `set`; the widening's picker
    keeps a tick across a frame that redraws the panel, sends nothing with none ticked, and *add*
    sends the pool's value now plus the pairings ticked; *Move back* sends `back_block` naming its
    suggestion. Each as the member signed in. Run in Chromium, and in WebKit (`WLX_BROWSER=webkit`),
    the engine of the PI's Safari."""
    rig.hub.offer(frame(**_TRAINING))
    page = rig.browser_page()
    _sign_in(page)
    # The trainer's panel is the Training tab's since the console settings build's Task 10 (its
    # design's §8).
    page.click('label[for="t-training"]')

    page.click('#rt-train [data-cmd="confirm"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 1)
    page.click('#rt-train [data-cmd="decline"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    page.click('#rt-train [data-cmd="lock"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 3)
    page.click('#rt-train [data-cmd="widen"]')
    page.locator("#sent", has_text="tick a pairing to add first").wait_for()
    page.check('#rt-train input[data-widen="8"]')
    # A frame redrawing the panel, as the next boundary's does with its bar's numbers moved.
    rig.hub.offer(frame(**{**_TRAINING, "suggestion": dataclasses.replace(_UP, correct=42)},
                        duration_warning=FRAME_MARKER))
    page.locator("#banners", has_text=FRAME_MARKER).wait_for(state="attached")
    page.locator("#rt-train", has_text="42 of the last 50").wait_for()
    kept = page.is_checked('#rt-train input[data-widen="8"]')
    page.click('#rt-train [data-cmd="widen"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 4)
    rig.hub.offer(frame(**{**_TRAINING, "widen": None, "suggestion": Suggestion(
        9, "back", "Fade-in", "Alone", 22, 50, False)}))
    page.locator('#rt-train [data-cmd="confirm"][data-move="back_block"]').wait_for()
    page.click('#rt-train [data-cmd="confirm"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 5)

    up, hold, lock, widened, back = rig.dispatch.seen
    assert (type(up), up.suggestion, up.by.name) == (NextBlock, 7, "Jake Westerberg")
    assert (type(hold), hold.suggestion, hold.by.name) == (Decline, 7, "Jake Westerberg")
    assert (type(lock), lock.name, lock.value) == (SetParameter, "distractor_luminance", 0.75)
    assert kept is True
    assert (type(widened), widened.name, widened.value) == (SetParameter, "pairings", 13)
    assert (type(back), back.suggestion) == (BackBlock, 9)


def test_freezing_from_the_training_tab_sends_shaping(rig):
    """**The training switch, from its own tab** (the console settings design's §8; the PI,
    2026-11-16: "a whole different tab ... easily toggleable"): the Runtime tab's one line names the
    switch and opens the Training tab; there *frozen* sends `shaping` `frozen` as the member signed
    in, staged to the next trial; and once the rig says it is frozen the switch shows it pressed,
    *full task* grayed where the plan declares none. Run in Chromium, and in WebKit
    (`WLX_BROWSER=webkit`), the engine of the PI's Safari."""
    rig.hub.offer(frame(**_TRAINING, shaping="on", full_task=True))
    page = rig.browser_page()
    _sign_in(page)

    page.locator("#rt-shaping", has_text="training on · stage Fade-in").wait_for()
    page.click('#rt-shaping label[for="t-training"]')
    opened = page.is_checked("#t-training")
    page.click('#shaping [data-cmd="shaping"][data-position="frozen"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 1)
    rig.hub.offer(frame(**_TRAINING, shaping="frozen", full_task=False))
    page.locator('#shaping [data-position="frozen"][aria-pressed="true"]').wait_for()
    page.locator('#shaping [data-position="full"][disabled]').wait_for(state="attached")
    page.locator("#rt-shaping", has_text="training frozen").wait_for(state="attached")

    (switched,) = rig.dispatch.seen
    assert opened is True
    assert (type(switched), switched.position, switched.by.name) == (
        Shaping, "frozen", "Jake Westerberg")


def test_the_pairings_are_picked_by_their_colors_names_at_the_start_and_on_the_panel(rig):
    """The pop-out search build's final fixes, 2 (Task 9's report: the trainer saw "pairing 1" to
    "pairing 12"): a pool whose looks are color-set lights names each pairing by its colors, the
    odd one's first, in the rig's own words (`task.Pool.named`). The trainer finds a pairing by
    those words -- each box's label, as a screen reader reads it -- ticks it at the run's start,
    which sends it among the run's values, and adds another at the panel's widening, which sends
    the pool's value now plus it. Run in Chromium, and in WebKit (`WLX_BROWSER=webkit`)."""
    from pathlib import Path

    from wl_xcon.photometry import ColorSet, ColorSetLight
    from wl_xcon.task import Disc, P, Pool

    isohue = ColorSet.load(Path(__file__).parent / "fixtures" / "isohue.json")
    disc = {(color, fraction): Disc(size=1.0, color=ColorSetLight(isohue, color, fraction))
            for color in isohue.colors for fraction in (1.0, P("distractor_fraction"))}
    pool = Pool("pairings", tuple(
        (disc[odd, 1.0], disc[among, P("distractor_fraction")])
        for odd, among in (("blue", "red"), ("red", "blue"), ("purple", "red"))),
        odd="odd_color", distractor="distractor_color")
    names = tuple(pool.named(at) for at in range(len(pool.choices)))
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    page = rig.browser_page()
    _sign_in(page)
    _preselected(rig, page)
    rig.hub.offer(_between_runs(offered_tasks=ONE_TASK, preflight=Preflight(
        "planned.py", PASSING, plan="train", plans=("train", "test"),
        stages=(StageRow("Alone"), StageRow("Crowd")), pool=PoolRow("pairings", names, 1))))
    page.click('label[for="t-setup"]')

    page.get_by_label("pairing red among blue", exact=True).check()
    page.click('[data-cmd="start"]')
    rig.wait_for(lambda: any(isinstance(seen, StartRun) for seen in rig.dispatch.seen))
    rig.hub.offer(frame(**{**_TRAINING, "suggestion": None,
                           "pool": Pooled("pairings", names, 3)}))
    # The trainer's panel is the Training tab's since the console settings build's Task 10.
    page.click('label[for="t-training"]')
    page.locator("#rt-train", has_text="pairings on blue among red, red among blue").wait_for()
    page.get_by_label("add pairing purple among red", exact=True).check()
    page.click('#rt-train [data-cmd="widen"]')
    rig.wait_for(lambda: any(isinstance(seen, SetParameter) for seen in rig.dispatch.seen))

    assert names == ("blue among red", "red among blue", "purple among red")
    (start,) = [seen for seen in rig.dispatch.seen if isinstance(seen, StartRun)]
    (widened,) = [seen for seen in rig.dispatch.seen if isinstance(seen, SetParameter)]
    assert start.values == {"pairings": 3}
    assert (widened.name, widened.value) == ("pairings", 7)


class _BoxRig:
    """The rig PC's own page: http on loopback, no wl.works sign-in, the operator named in the
    page's own storage (b3a-2)."""

    def __init__(self, browser) -> None:
        self.dispatch = _Dispatch()
        self.hub = Hub(steady=_Clock(), endpoint=ENDPOINT)
        port = int(free_endpoints(1)[0].rsplit(":", 1)[1])
        self.server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(
            self.hub, token=TOKEN, stale_after_s=30.0, dispatch=self.dispatch))
        self._thread = threading.Thread(target=self.server.serve_forever,
                                        kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()
        self._context = browser.new_context()
        self._context.add_init_script(
            "window.localStorage.setItem('wlx-console-name', 'Box Op')")
        self.page = _Opening(self._context.new_page())
        self.page.set_default_timeout(WAIT_S * 1000)
        self.url = f"http://127.0.0.1:{port}/"

    def wait_for(self, predicate, seconds: float = WAIT_S) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.05)
        pytest.fail(f"timed out after {seconds:g} s waiting for a condition")

    def close(self) -> None:
        for step in (self._context.close, self.server.shutdown, self.server.server_close,
                     self.hub.close):
            try:
                step()
            except Exception:
                pass


@pytest.fixture
def box():
    with browser() as launched:
        made = _BoxRig(launched)
        try:
            yield made
        finally:
            made.close()


def test_the_rig_pcs_own_page_preselects_the_first_plan_and_keeps_a_plain_choice(box):
    """The task's first review, fix round 2: the rig PC's page has no wl.works sign-in, so
    "signed in" was never true there and the preselection was never armed. It is armed where the
    page can send; the operator's own plain choice then stands."""
    box.hub.offer(_between_runs(offered_tasks=ONE_TASK))
    box.page.goto(box.url)
    box.page.wait_for_selector('[data-cmd="check"]:not([disabled])')
    box.page.click('[data-cmd="check"]')
    box.wait_for(lambda: len(_checks(box)) == 1)
    box.hub.offer(_plans_of(None))
    box.wait_for(lambda: len(_checks(box)) == 2)
    box.hub.offer(_plans_of("train"))
    box.page.wait_for_selector('[data-cmd="start"][data-plan="train"]:not([disabled])')
    box.page.select_option("#plan-sel", "")
    box.wait_for(lambda: len(_checks(box)) == 3)
    box.hub.offer(_plans_of(None))
    box.page.wait_for_selector('[data-cmd="start"][data-plan=""]:not([disabled])')
    box.hub.offer(_plans_of(None, stopped_because=FRAME_MARKER))
    _marker_shown(box.page)

    assert [(check.task, check.plan) for check in _checks(box)] == [
        ("planned.py", None), ("planned.py", "train"), ("planned.py", None)]
    assert box.page.evaluate('document.getElementById("plan-sel").value') == ""


# --- a server fault reads to the page as a lost answer (XC-042's backstop answers 500) -----------

_REWARD_LOST = (
    "unknown: this page lost wlx serve's answer, so whether the reward was given is not known, "
    "and it was not sent again; check the session's fluid total before pressing again"
)


def _after_a_reward_press(rig, make_it_fail) -> tuple[str, str, bool, bool]:
    """Press *give reward* with `make_it_fail(page)` in place; what the page says, in what class,
    whether the button is held, and whether the server was handed the command."""
    rig.hub.offer(frame(paused_at=1_700_000_030.0))
    page = rig.browser_page()
    _sign_in(page)
    rig.wait_for(lambda: not page.is_disabled(REWARD))
    make_it_fail(page)
    page.click(REWARD)
    rig.wait_for(lambda: page.evaluate("document.getElementById('sent').textContent") != "sending…")
    time.sleep(0.5)  # housekeeping: room for the line and the button to settle
    return (page.inner_text("#sent"), page.get_attribute("#sent", "class"),
            page.is_disabled(REWARD), bool(_rewards(rig)))


def test_a_reward_the_server_faulted_on_says_what_a_lost_answer_says(rig):
    """C1 of cli-refusals' review: at bcd2013 an answer the page lost to a server fault told the
    trainer the reward is unknown; the JSON 500 left the line blank."""
    rig.dispatch.raises = True
    said, klass, held, handed = _after_a_reward_press(rig, lambda page: None)

    assert handed, "the server was handed the reward before it faulted"
    assert said == _REWARD_LOST
    assert "crit" in klass


def test_a_reward_the_server_faulted_on_leaves_the_button_as_a_lost_answer_does(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with browser() as launched:
        lost = _Rig(tmp_path / "a", launched)
        try:
            lost_said = _after_a_reward_press(
                lost, lambda page: page.route("**/commands", lambda route: route.abort()))
        finally:
            lost.close()
        faulted = _Rig(tmp_path / "b", launched)
        try:
            faulted.dispatch.raises = True
            faulted_said = _after_a_reward_press(faulted, lambda page: None)
        finally:
            faulted.close()

    assert faulted_said[:3] == lost_said[:3]


def test_a_whoami_the_server_faulted_on_keeps_the_sign_in_and_asks_again(rig, monkeypatch):
    """I2: a rig that faulted is a rig that could not confirm, as one out of reach is."""
    page = rig.browser_page()
    _sign_in(page)

    def fault(*args, **kwargs):
        # An answer without a member: the handler raises reading it, after the request's body
        # was read, so the 500 reaches the page whole (a raise before that resets the
        # connection, which the page already read as a lost answer).
        return SimpleNamespace(expires_at=0)

    monkeypatch.setattr(rig.checker, "check", fault)
    page.reload()
    page.wait_for_selector("#sent:has-text('has not confirmed')")
    assert page.inner_text("#sent") == UNCONFIRMED
    assert _has_signin(page), "the sign-in is kept"
    assert "not signed in" not in page.inner_text("#sent")


# --- the rig's own 5xx answers carry a `said` and are shown as they were (fix round 2, C2) --------

_NO_ACK = (
    "not delivered: the rig did not acknowledge it within 5 s. It may still be applied at the "
    "rig's next trial boundary"
)


@pytest.mark.parametrize("answer", [
    pytest.param(serve.BUSY, id="busy-503"),
    pytest.param(serve.REWARD_UNKNOWN, id="reward-unknown-504"),
    pytest.param(serve.not_delivered("the rig is not connected; no reward was given"),
                 id="reward-not-delivered-504"),
])
def test_a_reward_answered_by_the_rig_with_a_5xx_shows_the_rigs_own_sentence(rig, answer):
    """At bcd2013 the page showed the answer's `said`, whatever the status: the PI's 2026-09-28
    line between 'not delivered' and 'unknown' on a reward is the rig's, not the page's."""
    rig.dispatch.answers = answer
    said, klass, _, handed = _after_a_reward_press(rig, lambda page: None)

    assert handed
    assert said == answer[1]["said"]
    assert "crit" in klass


def test_a_next_block_the_rig_may_still_apply_says_so(rig):
    """The worst case of reading every 5xx as lost: 'it may still be applied at the next trial
    boundary' became 'could not reach wlx serve', which invites a second press."""
    answer = serve.not_delivered(_NO_ACK[len("not delivered: "):])
    rig.dispatch.answers = answer
    rig.hub.offer(frame(plan="train", block="easy", next_block="hard"))
    page = rig.browser_page()
    _sign_in(page)
    page.wait_for_selector('[data-cmd="next_block"]', state="attached")
    page.click('[data-cmd="next_block"]')
    page.wait_for_selector("#sent:has-text('may still be applied')")

    assert page.inner_text("#sent") == answer[1]["said"]


def test_hand_back_a_range_and_revert_send_their_bodies(rig):
    """Engine build C3 (the PI, 2026-10-30, Q7a: "Yes, a 'hand back' button"; Q7b: "Yes, range
    changes live"; TSK-43, "Yes, with revert"): *hand back* on a card a person holds sends its
    setting's name, the box's Apply the numbers of the card's draw a person changed, by name, and
    *revert to this* its moment's change id, each reaching the rig as the signed-in member's.
    Rewritten for the console interface rework's Task 6: *change the range* is gone, the box's
    Apply its one send. Through the wire, in a real browser."""
    from wl_xcon.link import HandBack, MomentRow, ParamRow, Revert, SetRange, decode, encode

    rows = (
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.4, False, None, "person", ("near", "far")),
        ParamRow("wait", "s", 0.5, 2.0, None, False, None, "draw", (),
                 "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25}),
    )
    moments = (MomentRow(3, 1_700_000_030.0, "fix_hold 0.30 → 0.40", ("fix_hold → 0.30",)),
               MomentRow(0, 1_700_000_000.0, "the run's start", ("fix_hold → 0.30",)))
    rig.hub.offer(decode(encode(frame(params=rows, moments=moments))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)

    page.click('[data-cmd="hand_back"][data-name="fix_hold"]')
    rig.wait_for(lambda: rig.dispatch.seen)
    page.fill('#params input[data-number="high"]', "1.5")
    page.click('#params [data-apply="wait"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    page.click('#moments [data-cmd="revert"][data-change="3"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 3)

    handed, ranged, reverted = rig.dispatch.seen
    member = "Jake Westerberg"
    assert (type(handed), handed.name, handed.by.name) == (HandBack, "fix_hold", member)
    assert (type(ranged), ranged.name, ranged.numbers, ranged.by.name) == (
        SetRange, "wait", {"high": 1.5}, member)
    assert (type(reverted), reverted.change, reverted.by.name) == (Revert, 3, member)


def test_a_range_with_nothing_changed_or_a_word_for_a_number_is_not_sent(rig):
    """The page's own refusals of a range, each said and nothing sent, as a setting's are: a
    range none of whose numbers was changed -- `0.750` is the 0.75 shown -- is no draft at all,
    which would record a change that changed nothing, and a number that is not one is *cannot
    send*, its Apply off. Rewritten for the console interface rework's Task 6: the box's status
    line says it, where `#sent` did for *change the range*."""
    from wl_xcon.link import ParamRow, decode, encode

    row = ParamRow("wait", "s", 0.5, 2.0, None, False, None, "draw", (),
                   "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25})
    rig.hub.offer(decode(encode(frame(params=(row,)))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)

    page.fill('#params input[data-number="low"]', "0.750")
    assert "draft" not in _classes(page, "wait") and _bar(page) is None
    assert not page.is_visible('#params [data-apply="wait"]')
    page.fill('#params input[data-number="high"]', "soon")
    assert _say(page, "wait") == "cannot send · wait's high needs a number"
    assert page.is_disabled('#params [data-apply="wait"]')
    page.press('#params input[data-number="high"]', "Enter")
    time.sleep(0.3)  # housekeeping: room for a wrong send to arrive

    assert rig.dispatch.seen == []


def test_a_double_click_on_hand_back_change_the_range_or_revert_is_one_act(rig):
    """Each of the three is held as *clear one* is (the engine C2a plan's Task 9 fix round,
    Important 1): a double click, or two quick clicks, sends one command, never two -- a second
    hand-back the rig would refuse, a second range or revert it would record again. Rewritten for
    the console interface rework's Task 6: the range goes by the box's Apply, which is off while
    its act is out."""
    from wl_xcon.link import HandBack, MomentRow, ParamRow, Revert, SetRange, decode, encode

    rows = (
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.4, False, None, "person", ("near",)),
        ParamRow("wait", "s", 0.5, 2.0, None, False, None, "draw", (),
                 "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25}),
    )
    rig.hub.offer(decode(encode(frame(params=rows, moments=(
        MomentRow(0, 1_700_000_000.0, "the run's start", ("fix_hold → 0.30",)),)))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)

    page.dblclick('[data-cmd="hand_back"][data-name="fix_hold"]')
    rig.wait_for(lambda: rig.dispatch.seen)
    page.fill('#params input[data-number="high"]', "1.5")
    page.dblclick('#params [data-apply="wait"]', force=True)
    rig.wait_for(lambda: len(rig.dispatch.seen) >= 2)
    page.dblclick('#moments [data-cmd="revert"][data-change="0"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) >= 3)
    time.sleep(0.5)  # housekeeping: room for a wrong second send to arrive

    assert [type(seen) for seen in rig.dispatch.seen] == [HandBack, SetRange, Revert]


def test_a_range_typed_while_a_frame_arrives_is_still_sent_after_the_field_is_left(rig):
    """Fix round 1 of the C3 plan's Task 18 (review, Important 1): a person types a range's number,
    a frame that changes the cards arrives, and the field is left before the send is pressed -- in
    WebKit, Safari's engine, pressing a button does not focus it, so the press itself leaves the
    field. Rewritten for the console interface rework's Task 6 (the per-box rule): the frame is no
    longer held for the tab -- the other box shows it at once -- and the box typed in keeps its
    draft and its nodes, so its Apply sends the number typed."""
    from wl_xcon.link import ParamRow, SetRange, decode, encode

    def rows(hold):
        return (
            ParamRow("fix_hold", "s", 0.1, 1.0, hold, False, None, "run"),
            ParamRow("wait", "s", 0.5, 2.0, None, False, None, "draw", (),
                     "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25}),
        )

    rig.hub.offer(decode(encode(frame(params=rows(0.3)))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)

    page.fill('#params input[data-number="high"]', "1.5")
    _offer(rig, 41, params=rows(0.4))
    _arrived(page, 41)
    rig.wait_for(lambda: _head(page, "fix_hold") == "0.40 s")  # the other box follows the frame
    assert page.input_value('#params input[data-number="high"]') == "1.5"
    page.evaluate("document.activeElement.blur()")
    time.sleep(0.3)  # housekeeping: the focus-out's release runs on a timer
    page.click('#params [data-apply="wait"]')
    rig.wait_for(lambda: rig.dispatch.seen)

    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.numbers) == (SetRange, "wait", {"high": 1.5})
    assert not page.inner_text("#sent").startswith("not sent")
    assert page.inner_text("#sent") != ""


def test_a_card_updates_once_a_hand_back_or_a_range_has_applied(rig):
    """Fix round 1 of the C3 plan's Task 18 (review, Important 2): Chromium focuses a button it
    clicks, and the page held every parameter frame while anything inside the cards had focus, so
    after *hand back* or a range's send the card went on saying a person held the setting, with a
    live *hand back*, after the rig had applied it. A focused button keeps nothing; the boxes show
    the applied hand-back and the applied range. Rewritten for the console interface rework's
    Task 6: the range goes by its box's Apply, and its box keeps its act's numbers until the frame
    shows them in force."""
    from wl_xcon.link import HandBack, ParamRow, SetRange, decode, encode

    held = (ParamRow("fix_hold", "s", 0.1, 1.0, 0.4, False, None, "person", ("near",)),
            ParamRow("wait", "s", 0.5, 2.0, None, False, None, "draw", (),
                     "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25}))
    rig.hub.offer(decode(encode(frame(params=held))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)

    page.click('[data-cmd="hand_back"][data-name="fix_hold"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 1)
    page.fill('#params input[data-number="high"]', "1.5")
    page.click('#params [data-apply="wait"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    applied = (ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False, None, "conditions", ("near",)),
               ParamRow("wait", "s", 0.5, 2.0, None, False, None, "range", (),
                        "uniform from 0.75 s to 1.5 s", {"low": 0.75, "high": 1.5}))
    rig.hub.offer(decode(encode(frame(params=applied))))

    # `text_content`: the editor shows one box (the summary and editor design of 2026-11-19), and
    # `inner_text` reads no box it hides.
    rig.wait_for(lambda: "set or drawn by its conditions" in page.text_content("#params")
                 and page.input_value('#params input[data-number="high"]') == "1.5"
                 and _say(page, "wait") != "sending…")
    assert [type(seen) for seen in rig.dispatch.seen] == [HandBack, SetRange]
    assert 'data-cmd="hand_back"' not in page.inner_html("#params")
    assert "draft" not in _classes(page, "wait")


def _offer(rig, trial, **fields) -> None:
    """Offer the page a frame of `fields` marked as trial `trial`. The header's trial number is a
    pane no press and no typed number holds, so `_arrived` can wait on it (the final whole-branch
    review of engine build C3, Minor 2): a test that only slept before saying a frame was held
    passed, under load, on a frame that had not yet come."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(frame(trial_index=trial, **fields))))


def _arrived(page, trial) -> None:
    """Wait until the frame marked `trial` (`_offer`) has reached the page. One frame's panes are
    all swapped in, or held, by one handler, so the held panes have had it too."""
    page.wait_for_selector(f'#head-id [data-trial="{trial}"]', state="attached")


def _range_rows(hold=0.3):
    from wl_xcon.link import ParamRow

    return (
        ParamRow("fix_hold", "s", 0.1, 1.0, hold, False, None, "run"),
        ParamRow("wait", "s", 0.5, 2.0, None, False, None, "draw", (),
                 "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25}),
    )


def test_a_range_typed_and_left_unsent_says_not_sent_and_the_boxes_follow_the_frame(rig):
    """Was `test_a_range_typed_and_left_unsent_says_the_cards_wait_for_it` (fix round 2 of the C3
    plan's Task 18, New Breakage 1: never a silent freeze of the cards). Rewritten for the console
    interface rework's Task 6, whose per-box rule replaces the freeze: a number typed into a range
    and walked away from is a draft its box says is *not sent*, Apply live, while every other box
    follows the frame at once; put back, the draft goes."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(frame(params=_range_rows(0.3)))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)
    page.fill('#params input[data-number="high"]', "1.5")
    page.mouse.click(2, 2)  # a neutral spot: the field loses focus
    _offer(rig, 41, params=_range_rows(0.4))

    rig.wait_for(lambda: _head(page, "fix_hold") == "0.40 s")
    assert _say(page, "wait") == "not sent" and page.is_visible('#params [data-apply="wait"]')
    assert page.input_value('#params input[data-number="high"]') == "1.5"
    assert _bar(page) == "1 edit not sent: wait"

    page.fill('#params input[data-number="high"]', "1.25")
    assert "draft" not in _classes(page, "wait") and _bar(page) is None


def test_a_range_typed_as_the_same_number_does_not_hold_the_cards(rig):
    """Fix round 2 (New Breakage 1): "1.250" over 1.25 is the number in force, as the rig reads
    it, so it is no draft (the console interface rework's Task 6: "a draft equal to what is in
    force is no draft"): its box says nothing is waiting to be sent, and the boxes follow the next
    frame."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(frame(params=_range_rows(0.3)))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)
    page.fill('#params input[data-number="high"]', "1.250")
    page.mouse.click(2, 2)
    rig.hub.offer(decode(encode(frame(params=_range_rows(0.4)))))

    rig.wait_for(lambda: "0.40" in page.text_content("#params"))
    assert "draft" not in _classes(page, "wait") and _bar(page) is None


def test_a_range_press_the_rig_did_not_take_can_be_sent_again(rig):
    """Fix round 2 (New Breakage 2): the typed numbers count as sent only when the answer says
    "sent". After "not delivered" the box has its draft back, saying why, and the same Apply
    sends it again. Rewritten for the console interface rework's Task 6: the box's Apply for *change
    the range*, its status line for `#sent`."""
    from wl_xcon.link import SetRange, decode, encode
    from wl_xcon import serve

    rig.hub.offer(decode(encode(frame(params=_range_rows()))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)
    rig.dispatch.answers = serve.not_delivered("the rig is not connected")
    page.fill('#params input[data-number="high"]', "1.5")
    page.click('#params [data-apply="wait"]')
    _says(rig, page, "wait", "not sent · not delivered", start=True)
    assert not page.is_disabled('#params [data-apply="wait"]')
    rig.dispatch.answers = None
    page.click('#params [data-apply="wait"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)

    assert [seen.numbers for seen in rig.dispatch.seen] == [{"high": 1.5}, {"high": 1.5}]
    assert [type(seen) for seen in rig.dispatch.seen] == [SetRange, SetRange]


def test_a_press_is_not_lost_when_a_frame_lands_between_the_mouse_down_and_up(rig):
    """Fix round 2 (New Breakage 3): the cards and the moments pane are held while a pointer is
    down inside them, so a frame that changes them mid-press does not replace the button under the
    mouse (WebKit never focused it; Chromium's focus no longer holds the cards). Both presses
    arrive."""
    from wl_xcon.link import HandBack, MomentRow, ParamRow, Revert

    def offer(trial, hold, moments):
        rows = (ParamRow("fix_hold", "s", 0.1, 1.0, 0.4, False, None, "person", ("near",)),
                ParamRow("gain", "", None, None, hold, False, None, "run"))
        _offer(rig, trial, params=rows, moments=moments)

    first = (MomentRow(3, 1_700_000_030.0, "fix_hold 0.30 → 0.40", ("fix_hold → 0.30",)),)
    offer(40, 2.0, first)
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)

    page.hover('[data-cmd="hand_back"][data-name="fix_hold"]')
    page.mouse.down()
    offer(41, 3.0, first)
    _arrived(page, 41)
    assert "2.00" in page.text_content("#params")  # held under the press
    page.mouse.up()
    rig.wait_for(lambda: len(rig.dispatch.seen) == 1)

    page.hover('#moments [data-cmd="revert"][data-change="3"]')
    page.mouse.down()
    offer(42, 3.0, (MomentRow(5, 1_700_000_090.0, "gain 3.00 → 4.00", ("gain → 4.00",)),) + first)
    _arrived(page, 42)
    assert "gain 3.00 → 4.00" not in page.inner_text("#moments")  # held under the press
    page.mouse.up()
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)

    assert [type(seen) for seen in rig.dispatch.seen] == [HandBack, Revert]
    assert rig.dispatch.seen[1].change == 3


def _gain_rows(gain):
    from wl_xcon.link import ParamRow

    return (ParamRow("fix_hold", "s", 0.1, 1.0, 0.4, False, None, "person", ("near",)),
            ParamRow("gain", "", None, None, gain, False, None, "run"))


def _moment(change, said):
    from wl_xcon.link import MomentRow

    return MomentRow(change, 1_700_000_000.0 + change, said, (said + " back",))


def test_an_older_held_frame_never_replaces_a_newer_one_after_a_press_expires(rig):
    """Fix round 3 of the C3 plan's Task 18 (re-review 2, New Breakage 1): a press that expired
    without a release held a frame (gain 3.00, a moment); the next frame (4.00, a newer moment)
    was shown, yet the older stayed in the held copy and the next release wrote it back over the
    newer, in the cards and the moments pane alike. A frame shown clears the held copy. The page's
    clock is set by hand here so that the press has expired and no timer has run."""
    from wl_xcon.link import decode, encode

    first, second = _moment(3, "fix_hold 0.30 to 0.40"), _moment(5, "gain 3.00 to 4.00")
    rig.hub.offer(decode(encode(frame(params=_gain_rows(2.0), moments=(first,)))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)
    page.evaluate("window.__t = performance.now(); performance.now = function () { return window.__t; };")

    page.hover('[data-cmd="hand_back"][data-name="fix_hold"]')
    page.mouse.down()
    _offer(rig, 41, params=_gain_rows(3.0), moments=(_moment(4, "gain 2.00 to 3.00"), first))
    _arrived(page, 41)
    assert "2.00" in page.text_content("#params") and "gain 2.00" not in page.inner_text("#moments")
    page.evaluate("window.__t += 10001")
    _offer(rig, 42, params=_gain_rows(4.0), moments=(second, first))
    rig.wait_for(lambda: "4.00" in page.text_content("#params"))
    # The focus-out's release runs on a timer of 0 ms; this returns once a later one has run.
    page.evaluate("() => { document.dispatchEvent(new Event('focusout'));"
                  " return new Promise(function (done) { setTimeout(done, 50); }); }")

    assert "4.00" in page.text_content("#params") and "3.00" not in page.text_content("#params")
    assert "gain 3.00 to 4.00" in page.inner_text("#moments")


def test_a_press_the_page_never_sees_end_shows_the_held_frame(rig):
    """Fix round 3 (New Breakage 1): a press ended by the window losing focus shows the held frame
    at once, and one whose release the page never sees (outside the window) shows it when the
    ten seconds it may hold the cards are up -- the cards are not left stale."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(frame(params=_gain_rows(2.0)))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)

    page.hover('[data-cmd="hand_back"][data-name="fix_hold"]')
    page.mouse.down()
    _offer(rig, 41, params=_gain_rows(3.0))
    _arrived(page, 41)
    assert "2.00" in page.text_content("#params")
    page.evaluate("window.dispatchEvent(new Event('blur'))")
    rig.wait_for(lambda: "3.00" in page.text_content("#params"), seconds=4)
    page.mouse.up()

    page.hover('[data-cmd="hand_back"][data-name="fix_hold"]')
    page.mouse.down()
    _offer(rig, 42, params=_gain_rows(4.0))
    _arrived(page, 42)
    assert "3.00" in page.text_content("#params")
    rig.wait_for(lambda: "4.00" in page.text_content("#params"), seconds=14)


def test_a_correction_typed_while_a_range_press_is_out_stays_to_be_sent(rig):
    """Fix round 3 (New Breakage 2): the rig answers a range at its next trial boundary. A number
    typed meanwhile (1.6 after 1.5 was sent) is not what was sent, so once the rig stages the
    first it is a draft over it, saying the first waits, and its Apply sends it. Rewritten for the
    console interface rework's Task 6: the box keeps its nodes while its act is out."""
    from wl_xcon.actor import Box
    from wl_xcon.link import SetRange, Staged, decode, encode

    rig.hub.offer(decode(encode(frame(params=_range_rows()))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)
    rig.dispatch.delay = 3.0
    page.fill('#params input[data-number="high"]', "1.5")
    page.click('#params [data-apply="wait"]')
    rig.wait_for(lambda: rig.dispatch.seen)
    page.fill('#params input[data-number="high"]', "1.6")
    assert _say(page, "wait") == "sending…"
    page.wait_for_selector("#sent:has-text('sent: test')", timeout=10000)
    rig.dispatch.delay = 0.0
    _offer(rig, 41, params=_range_rows(), staged=(Staged(
        "wait", "uniform from 0.75 s to 1.25 s", "uniform from 0.75 s to 1.5 s", Box("Jake Westerberg"),
        False, kind="range", cid=rig.dispatch.seen[-1].cid),))

    _says(rig, page, "wait", "not sent · range uniform from 0.75 s to 1.5 s is waiting")
    page.click('#params [data-apply="wait"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    assert [seen.numbers for seen in rig.dispatch.seen if isinstance(seen, SetRange)] == [
        {"high": 1.5}, {"high": 1.6}]


def test_a_second_apply_while_the_first_is_out_is_held_off_and_the_box_says_sending(rig):
    """Was `test_a_second_range_press_while_the_first_is_out_is_refused_and_said` (fix round 3, New
    Breakage 3: while a card's range is out and unanswered, a second press is not sent again).
    Rewritten for the console interface rework's Task 6: the box says *sending…* and its Apply is
    off while its act is out (the controls review's §2, rule 5), so a second press sends
    nothing."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(frame(params=_range_rows()))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)
    rig.dispatch.delay = 3.0
    page.fill('#params input[data-number="high"]', "1.5")
    page.click('#params [data-apply="wait"]')
    rig.wait_for(lambda: rig.dispatch.seen)
    time.sleep(1.3)  # housekeeping: past a double click's span
    assert _say(page, "wait") == "sending…"
    assert page.is_disabled('#params [data-apply="wait"]')
    page.click('#params [data-apply="wait"]', force=True)
    page.wait_for_selector("#sent:has-text('sent: test')", timeout=10000)

    assert len(rig.dispatch.seen) == 1


@pytest.mark.parametrize("ending", ["contextmenu", "dragstart", "middle"])
def test_a_press_a_menu_or_a_drag_takes_over_or_no_primary_press_leaves_the_cards_live(
        rig, ending):
    """The C3 plan's Task 18, its deferred minor (re-review 3, New Breakage 1; probes h1 to h3): a
    press on *hand back* holds the cards, and a card-changing frame that arrives under it is shown
    as soon as the press ends some way other than its pointer going up -- a context menu (on
    macOS a Control-click is button 0 and then `contextmenu`) or a drag taking it over -- and a
    press of any button but the primary holds nothing. Each frame shows within 4 s, where the
    hold would otherwise leave the cards stale until its 10 s expiry. The events are synthetic:
    a Control-click fires `contextmenu` only on macOS, and Playwright fires no `dragstart`."""
    _offer(rig, 40, params=_gain_rows(2.0))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)
    button = '[data-cmd="hand_back"][data-name="fix_hold"]'

    page.hover(button)
    page.mouse.down(button="middle" if ending == "middle" else "left")
    _offer(rig, 41, params=_gain_rows(3.0))
    _arrived(page, 41)
    if ending == "contextmenu":
        assert "2.00" in page.text_content("#params")  # held under the press
        page.evaluate("(b) => document.querySelector(b).dispatchEvent(new MouseEvent("
                      "'contextmenu', {bubbles: true, cancelable: true}))", button)
    elif ending == "dragstart":
        assert "2.00" in page.text_content("#params")  # held under the press
        page.evaluate("(b) => document.querySelector(b).dispatchEvent(new Event("
                      "'dragstart', {bubbles: true}))", button)

    rig.wait_for(lambda: "3.00" in page.text_content("#params"), seconds=4)
    page.mouse.up(button="middle" if ending == "middle" else "left")


def test_a_double_click_on_change_the_range_never_says_not_sent_while_the_rig_answers(rig):
    """The C3 plan's Task 18, its deferred minor (re-review 3, minor 2): the rig answers a range at
    its next trial boundary, and a double click's second press said in red "not sent: the range
    of wait is still being sent" until the answer came, though the range was sent. Rewritten for
    the console interface rework's Task 6, where the box's Apply sends the range: neither `#sent`
    nor the box's status line ever reads "not sent" -- each text shown is kept as it is shown --
    and one range is sent."""
    from wl_xcon.link import SetRange, decode, encode

    rig.hub.offer(decode(encode(frame(params=_range_rows()))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    _more(page)
    page.fill('#params input[data-number="high"]', "1.5")
    page.evaluate("""() => {
      window.__said = [];
      const keep = () => {
        window.__said.push(document.getElementById('sent').textContent);
        const say = document.querySelector('#params .box[data-card="wait"] > .status > .say');
        if (say) { window.__said.push(say.textContent); }
      };
      new MutationObserver(keep).observe(document.getElementById('sent'),
        {childList: true, characterData: true, subtree: true});
      new MutationObserver(keep).observe(document.getElementById('params'),
        {childList: true, characterData: true, subtree: true});
    }""")
    rig.dispatch.delay = 3.0
    page.dblclick('#params [data-apply="wait"]', force=True)
    page.wait_for_selector("#sent:has-text('sent: test')", timeout=10000)
    rig.dispatch.delay = 0.0

    said = page.evaluate("window.__said")
    # Before the press the box rightly says its draft is *not sent*; from the press on, never.
    assert "sending…" in said and "sent: test" in said
    after = said[said.index("sending…"):]
    assert [line for line in after if line.startswith("not sent")] == []
    assert [type(seen) for seen in rig.dispatch.seen] == [SetRange]


# --- A demo (demo mode §4.1-§4.6; its plan's Task 9) --------------------------------------------
#
# Two rigs. **A stand-in** (`_DemoBox`): the rig PC's own page over a real `wlx serve` handler
# whose steer is `_Steer`, which keeps each report as `parse_gaze` read it, and a hub offered a
# demo session's frame and a screen drawn by the real `demoscreen.Drawer`: for what the page sends
# and says. **A live demo** (`_LiveDemo`): a demo service in process over the real link
# (`tests/_demo.Demo`, its scripted pointer left out), `wlx serve` on its four endpoints, and the
# page at `#demo`, full-window, the person Playwright's mouse and keyboard: the pop-out played
# through the rig's own eye rules. Engine test material: the wall-clock pacing makes a trial run
# as a person's does, and no timing claim rests on it (CLAUDE.md).

#: A demo's session, as `wlx demo` names one.
DEMO_SESSION = "demo-20261114-120000"
#: The browser's window, as a person's might be: the full-window view letterboxes the drawing in it.
WINDOW = {"width": 1280, "height": 720}
#: How close the page's degrees must be to Python's at the same pixel: far under a pixel (about
#: 0.05° here), far over float rounding, and far under what an average pixels-per-degree would
#: be off by at the positions read (each test checks that it would be).
DEGREES_EXACT = 1e-3
#: **A hand's glide**: the mouse moved along a straight path for this many seconds, each move to
#: where the hand would be by then, as often as Playwright moves it (about once an animation frame
#: in Chromium, faster in WebKit), so every frame of the glide holds a move, as a mouse's events
#: do; the page reports one each frame, and the rig eases them into one path its saccade detector
#: sees whole. Found here: moves a fixed 15 ms apart left frames with none, the page sent no report
#: in them, and the eased path stopped between two, which the detector read as two saccades (a
#: correct answer scored a second look, an abort); and 24 moves a frame each took 0.4 s, a 20°/s
#: drift near the detector's threshold. Engine test material, claiming nothing about a hand.
GLIDE_S = 0.1
#: Between two moves of a glide, when Playwright returns at once: about a mouse's event interval.
GLIDE_STEP_S = 0.002
#: **A flick**, for an answer that must reach the rig as one saccade: the mouse moved at once, this
#: long after the page's last report, so the one report that carries the whole move is eased by
#: the rig over the time since the one before (`pointer.Source`), as `tests/_demo.py`'s scripted
#: pointer flicks. A glide reported a frame at a time is a saccade on a quiet machine, and split in
#: two under the suite's load until `pointer.EASE_SLACK_S` (2026-11-16, the build's review, I2,
#: whose glide test is `tests/test_pointer.py`'s, on an injected clock); a flick stays the answer
#: here, where the suite's load is on the wall clock. Engine test material.
FLICK_AFTER_S = 0.06


class _Steer:
    """What `Server.steer` would be (demo mode §4.5): each report and release, as `parse_gaze`
    read it, kept in order and answered `answer` (*sent* unless a test says otherwise; a release
    `RELEASED`), after `delay` seconds; and the most that were ever in flight at once."""

    def __init__(self) -> None:
        self.seen: list = []
        self.answer: tuple[int, dict] = (200, {"status": "sent", "said": serve.GAZE_SENT})
        self.delay = 0.0
        self.most = 0
        self._flying = 0
        self._lock = threading.Lock()

    def __call__(self, report):
        with self._lock:
            self._flying += 1
            self.most = max(self.most, self._flying)
        try:
            if self.delay:
                time.sleep(self.delay)
            self.seen.append(report)
            return serve.RELEASED if isinstance(report, GazeRelease) else self.answer
        finally:
            with self._lock:
                self._flying -= 1

    def reports(self) -> list:
        return [seen for seen in self.seen if isinstance(seen, GazeReport)]

    def releases(self) -> list:
        return [seen for seen in self.seen if isinstance(seen, GazeRelease)]


def _screen(geometry=DIRECT, *, session: str = DEMO_SESSION, keys=()) -> Drawn:
    """A demo's screen as `pointer.Drawing` publishes one: a fixation disc, on the test rig's
    direct view (its stand-in housings) or its stereoscope."""
    shown = {"fix": Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.5, color=Gray(40.0)))}
    return Drawn(
        schema=SCHEMA, phase="drawn", session_id=session, trial=0, frame=1,
        screen=screens.resolve(shown, {}, Trial(start="s", states=[]), geometry,
                               frame_period=1 / 240, frame=1, calibration=SRGB),
        windows=(), outlines=(), viewports=viewport.viewports(RIG, geometry),
        housings=tuple(geometry.housings), stand_in=geometry.view == "direct",
        mask_deg=geometry.mask_deg, keys=keys, vergence_half_deg=geometry.vergence_half_deg,
    )


class _DemoBox:
    """The rig PC's own page, steering a stand-in (`_Steer`): http on loopback, the operator named
    in the page's storage, a console with the demo's gaze endpoint."""

    def __init__(self, browser) -> None:
        self.dispatch = _Dispatch()
        self.steer = _Steer()
        self.hub = Hub(steady=_Clock(), endpoint=ENDPOINT, gaze=True)
        port = int(free_endpoints(1)[0].rsplit(":", 1)[1])
        self.server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(
            self.hub, token=TOKEN, stale_after_s=30.0, dispatch=self.dispatch, steer=self.steer))
        self._thread = threading.Thread(target=self.server.serve_forever,
                                        kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()
        self._context = browser.new_context(viewport=WINDOW)
        self._context.add_init_script("window.localStorage.setItem('wlx-console-name', 'Box Op')")
        # What the page's Content-Security-Policy refused, by directive: a demo's drawing needs
        # its `data:` images.
        self._context.add_init_script(
            "window.wlxBlocked = []; document.addEventListener('securitypolicyviolation',"
            " (e) => window.wlxBlocked.push(e.violatedDirective));")
        self.page = _Opening(self._context.new_page())
        self.page.set_default_timeout(WAIT_S * 1000)
        self.url = f"http://127.0.0.1:{port}/"

    def demo(self, geometry=DIRECT, *, keys=()) -> Drawn:
        """A demo session running, and its screen drawn and shown on the page."""
        shown = _screen(geometry, keys=keys)
        self.hub.offer(frame(demo=True, service=True, session_id=DEMO_SESSION))
        self.hub.offer_drawn(shown)
        return shown

    def wait_for(self, predicate, seconds: float = WAIT_S) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.05)
        pytest.fail(f"timed out after {seconds:g} s waiting for a condition")

    def close(self) -> None:
        for step in (self._context.close, self.server.shutdown, self.server.server_close,
                     self.hub.close):
            try:
                step()
            except Exception:
                pass


@pytest.fixture
def demo_box():
    with browser() as launched:
        made = _DemoBox(launched)
        try:
            yield made
        finally:
            made.close()


@pytest.fixture
def gaze_rig(tmp_path):
    """The https page of a rig whose console has the demo's gaze endpoint."""
    with browser() as launched:
        made = _Rig(tmp_path, launched, gaze=True)
        try:
            yield made
        finally:
            made.close()


_DRAWN = "#demo-drawing:not([hidden]) svg g.eye"


def _box_of(page, selector: str) -> dict:
    return page.locator(selector).bounding_box()


def _expected(page, svg_text: str):
    """**The pointer in degrees, computed by Python apart from the page's script**: the drawing's
    box as the browser laid it out, its viewBox fitted in it (`xMidYMid meet`, SVG's default), each
    eye's group placed by its own `transform` attribute and its `data-distance-cm`, and `geometry`'s
    rule, `atan(x_cm / D)` per axis (`demoscreen.degrees_of`). Returns `(to_degrees, to_pixels,
    linear)`: a client pixel's degrees and which eye, a position's client pixel in an eye, and what
    an average pixels-per-degree would say at a pixel -- the rule the PI retired, 2026-10-19."""
    root = ET.fromstring(svg_text)
    x0, y0, width, height = (float(v) for v in root.get("viewBox").split())
    eyes = []
    for group in root.findall("{http://www.w3.org/2000/svg}g[@class='eye']"):
        tx, ty = (float(v) for v in re.match(r"translate\(([^,]+),([^)]+)\)",
                                             group.get("transform")).groups())
        image = group.find("{http://www.w3.org/2000/svg}image[@class='frame']")
        left = tx + float(image.get("x"))
        eyes.append((group.get("data-eye"), tx, ty, float(group.get("data-distance-cm")),
                     left, left + float(image.get("width"))))
    box = page.evaluate(
        "(() => { const r = document.querySelector('#demo-drawing svg').getBoundingClientRect();"
        " return [r.left, r.top, r.width, r.height]; })()")
    scale = min(box[2] / width, box[3] / height)
    ox = box[0] + (box[2] - width * scale) / 2 - x0 * scale
    oy = box[1] + (box[3] - height * scale) / 2 - y0 * scale

    def eye_of(ux):
        return min(eyes, key=lambda e: 0.0 if e[4] <= ux <= e[5] else min(abs(ux - e[4]),
                                                                         abs(ux - e[5])))

    def to_degrees(px, py):
        ux, uy = (px - ox) / scale, (py - oy) / scale
        name, tx, ty, d, _, _ = eye_of(ux)
        x_cm, y_cm = ux - tx, ty - uy
        return name, (math.degrees(math.atan(x_cm / d)), math.degrees(math.atan(y_cm / d)))

    def to_pixels(name, x_deg, y_deg):
        _, tx, ty, d, _, _ = next(e for e in eyes if e[0] == name)
        x_cm, y_cm = d * math.tan(math.radians(x_deg)), d * math.tan(math.radians(y_deg))
        return ox + (x_cm + tx) * scale, oy + (ty - y_cm) * scale

    def linear(px, py):
        ux, uy = (px - ox) / scale, (py - oy) / scale
        _, tx, ty, d, _, _ = eye_of(ux)
        per_cm = math.degrees(1.0 / d)  # degrees per centimeter at the eye's straight-ahead point
        return (ux - tx) * per_cm, (ty - uy) * per_cm

    return to_degrees, to_pixels, linear


def _report_after(box, count: int, seconds: float = WAIT_S) -> GazeReport:
    """The latest report once two more than `count` have come: the pointer is still, so at least
    two reports a `GAZE_EVERY_MS` apart carry where it rests."""
    box.wait_for(lambda: len(box.steer.reports()) >= count + 2, seconds)
    return box.steer.reports()[-1]


@pytest.mark.parametrize("geometry", [DIRECT, STEREOSCOPE], ids=["direct", "stereoscope"])
def test_the_page_turns_the_pointer_into_degrees_as_python_does(demo_box, geometry):
    """§3.3, §4.4 (the PI, 2026-10-19: no average ppd): the page reports the pointer in degrees
    read from the drawing's own eye group, `atan(x_cm / D)` per axis, +y up, in the eye it is over
    -- the same number Python computes at that pixel from the layout, the transform and `D`, apart
    from the script, in the pane and in the full window's letterbox; off the drawing it reports
    `over` false. At each position read off-center, an average pixels-per-degree would be wrong by
    many times the tolerance, so the test tells the two rules apart."""
    page = demo_box.page
    page.goto(demo_box.url)
    shown = demo_box.demo(geometry)
    page.wait_for_selector(_DRAWN, state="attached")
    svg = demoscreen.render(shown)
    names = [vp.eye for vp in shown.viewports]
    targets = ([(names[0], 0.0, 0.0), (names[0], 12.0, -6.0), (names[0], -20.0, 8.0)]
               if len(names) == 1 else
               [("left", -10.0, 8.0), ("right", 11.0, -9.0), ("right", -9.0, 10.0)])
    for full in (False, True):
        if full:
            page.keyboard.press("f")
            page.wait_for_selector("#demo-pane.full", state="attached")
        to_degrees, to_pixels, linear = _expected(page, svg)
        for name, x_deg, y_deg in targets:
            px, py = (round(v) for v in to_pixels(name, x_deg, y_deg))
            count = len(demo_box.steer.reports())
            page.mouse.move(px, py)
            said = _report_after(demo_box, count)
            eye, (want_x, want_y) = to_degrees(px, py)
            assert eye == name and said.over is True, (full, name, x_deg, y_deg)
            assert abs(said.x - want_x) < DEGREES_EXACT and abs(said.y - want_y) < DEGREES_EXACT, (
                full, name, (x_deg, y_deg), (said.x, said.y), (want_x, want_y))
            assert abs(said.x - x_deg) < 0.2 and abs(said.y - y_deg) < 0.2, "a pixel's worth"
            if (x_deg, y_deg) != (0.0, 0.0):
                flat_x, flat_y = linear(px, py)
                assert max(abs(flat_x - said.x), abs(flat_y - said.y)) > 20 * DEGREES_EXACT
    # Off the drawing, in the full window's bar: gaze away, never a position; and out of the
    # window (as the browser says, which Playwright's mouse cannot leave): gaze away too.
    bar = _box_of(page, ".demo-bar")
    count = len(demo_box.steer.reports())
    page.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2)
    said = _report_after(demo_box, count)
    assert (said.over, said.x, said.y) == (False, 0.0, 0.0)
    page.mouse.move(*(round(v) for v in to_pixels(names[0] if len(names) == 1 else "right",
                                                   1.0, 1.0)))
    _report_after(demo_box, len(demo_box.steer.reports()))
    assert demo_box.steer.reports()[-1].over is True
    page.evaluate("document.body.dispatchEvent(new MouseEvent('mouseout', {bubbles: true,"
                  " relatedTarget: null}))")
    assert _report_after(demo_box, len(demo_box.steer.reports())).over is False
    # The drawing's frames are images from `data:`, which the page's policy admits.
    assert page.evaluate("window.wlxBlocked") == []


def test_keys_do_nothing_while_typing_in_a_box(demo_box):
    """§4.6: the number keys and B are the demo's only over the drawing or in the full window, and
    never while typing in a box -- where P and M are not taken either. Over the drawing, out of a
    box, a key is held while down and counted once a press; B is held while down."""
    page = demo_box.page
    page.goto(demo_box.url)
    demo_box.demo(keys=("lever",))
    page.wait_for_selector(_DRAWN, state="attached")
    page.wait_for_selector("#demo-keys kbd:text-is('1')", state="attached")
    screen = _box_of(page, "#demo-drawing svg")
    page.mouse.move(screen["x"] + screen["width"] / 2, screen["y"] + screen["height"] / 2)
    demo_box.wait_for(lambda: len(demo_box.steer.reports()) >= 2)

    page.fill("#run-trials", "")  # focuses the box, empty
    for key in ("1", "b", "B", "9", "p", "m"):
        page.keyboard.press(key)
    page.keyboard.down("2")
    page.keyboard.down("b")
    said = _report_after(demo_box, len(demo_box.steer.reports()))
    page.keyboard.up("2")
    page.keyboard.up("b")
    assert (said.held, said.presses, said.b) == (0, (0,) * 9, False)
    assert page.input_value("#run-trials") == "1bB9pm2b", "the keys went to the box"
    assert not [seen for seen in demo_box.dispatch.seen if isinstance(seen, Pause)]

    page.evaluate("document.activeElement.blur()")
    page.mouse.move(screen["x"] + screen["width"] / 2, screen["y"] + screen["height"] / 2 + 1)
    page.keyboard.down("1")
    page.keyboard.down("b")
    held = _report_after(demo_box, len(demo_box.steer.reports()))
    page.keyboard.up("1")
    page.keyboard.up("b")
    let_go = _report_after(demo_box, len(demo_box.steer.reports()))
    assert (held.held, held.presses[0], held.b) == (1, 1, True)
    assert (let_go.held, let_go.presses[0], let_go.b) == (0, 1, False)

    # Off the drawing, the pane not full: a key is no demo's.
    page.mouse.move(5, 5)
    page.keyboard.press("1")
    off = _report_after(demo_box, len(demo_box.steer.reports()))
    assert off.over is False and off.presses[0] == 1

    # The mouse button, over the drawing: a touch while it is down (the click opens the full
    # window too).
    page.mouse.move(screen["x"] + screen["width"] / 2, screen["y"] + screen["height"] / 2)
    page.mouse.down()
    pressed = _report_after(demo_box, len(demo_box.steer.reports()))
    page.mouse.up()
    released = _report_after(demo_box, len(demo_box.steer.reports()))
    assert (pressed.button, released.button, released.over) == (True, False, True)


def test_a_page_says_steered_from_another_page_and_lets_go_on_escape_and_when_it_goes(demo_box):
    """§4.5: a report answered 409 *steered from another page* is said so; Escape lets go of the
    eye (`release`), and nothing more is sent until the pointer moves again; the page going away
    lets go too (`fetch` with `keepalive`). One report is in flight at a time, at most one an
    animation frame while the pointer moves."""
    page = demo_box.page
    page.goto(demo_box.url)
    demo_box.demo()
    page.wait_for_selector(_DRAWN, state="attached")
    screen = _box_of(page, "#demo-drawing svg")
    middle = (screen["x"] + screen["width"] / 2, screen["y"] + screen["height"] / 2)

    demo_box.steer.answer = serve.STEERED_ELSEWHERE
    page.mouse.move(*middle)
    page.wait_for_selector('#demo-pane[data-steer="elsewhere"]', state="attached")
    assert page.inner_text("#demo-steer").startswith("steered from another page")
    assert "warn" in page.get_attribute("#demo-steer", "class")

    demo_box.steer.answer = (200, {"status": "sent", "said": serve.GAZE_SENT})
    demo_box.steer.delay = 0.05
    for step in range(30):
        page.mouse.move(middle[0] + step, middle[1])
        time.sleep(0.005)
    page.wait_for_selector('#demo-pane[data-steer="steering"]', state="attached")
    assert demo_box.steer.most == 1, "one report in flight at a time"
    seqs = [report.seq for report in demo_box.steer.reports()]
    assert seqs == sorted(set(seqs)), "each report's seq rises"
    demo_box.steer.delay = 0.0
    # At most once an animation frame: moves every 2 ms for 0.3 s, the rig answering at once,
    # are at most a report a frame (60 a second, and a few for the frames' edges).
    before = len(demo_box.steer.reports())
    page.evaluate(
        "() => new Promise((done) => { const at = performance.now(); const tick = setInterval(() => {"
        " const t = performance.now() - at; document.dispatchEvent(new PointerEvent('pointermove',"
        " {clientX: %f + t / 10, clientY: %f, bubbles: true}));"
        " if (t > 300) { clearInterval(tick); done(); } }, 2); })" % middle)
    time.sleep(0.15)
    moved = len(demo_box.steer.reports()) - before
    assert 3 <= moved <= 0.45 * 60 + 4, moved

    page.keyboard.press("Escape")
    demo_box.wait_for(lambda: len(demo_box.steer.releases()) == 1)
    quiet = len(demo_box.steer.reports())
    time.sleep(0.4)
    assert len(demo_box.steer.reports()) <= quiet + 1, "nothing after Escape but one in flight"
    page.mouse.move(middle[0], middle[1] + 3)
    demo_box.wait_for(lambda: len(demo_box.steer.reports()) > quiet + 1)

    page.goto("about:blank")
    demo_box.wait_for(lambda: len(demo_box.steer.releases()) == 2)
    assert {release.page for release in demo_box.steer.releases()} == {
        demo_box.steer.reports()[0].page}


#: **The tab hidden, or shown again**, as the browser says it: `document.visibilityState` set and
#: `visibilitychange` sent, which is what a page sees when its tab goes behind another or comes back
#: (Playwright has no call that hides a page; this is the event the page listens for).
_VISIBILITY = (
    "(state) => { Object.defineProperty(document, 'visibilityState',"
    " {configurable: true, get: () => state});"
    " document.dispatchEvent(new Event('visibilitychange')); }")


def test_a_hidden_tab_lets_go_of_the_eye_and_steers_again_once_the_pointer_moves(demo_box):
    """The build's re-review, N1: a hidden tab's timers are throttled, not stopped, so a still
    pointer's reports would go on and let a trial through each boundary to end as tracker lost.
    **Hidden, the page lets go as Escape does** (`release`), and sends nothing more, its timer
    running or not; shown again, still nothing until the pointer moves on it, and then it steers."""
    page = demo_box.page
    page.goto(demo_box.url)
    demo_box.demo()
    page.wait_for_selector(_DRAWN, state="attached")
    screen = _box_of(page, "#demo-drawing svg")
    middle = (screen["x"] + screen["width"] / 2, screen["y"] + screen["height"] / 2)
    page.mouse.move(*middle)
    page.wait_for_selector('#demo-pane[data-steer="steering"]', state="attached")
    demo_box.wait_for(lambda: len(demo_box.steer.reports()) >= 3)

    page.evaluate(_VISIBILITY, "hidden")
    demo_box.wait_for(lambda: len(demo_box.steer.releases()) == 1)
    quiet = len(demo_box.steer.reports())
    time.sleep(0.5)  # five of the still pointer's report intervals (`GAZE_EVERY_MS`)
    assert len(demo_box.steer.reports()) <= quiet + 1, "nothing while hidden but one in flight"
    page.evaluate(_VISIBILITY, "visible")
    time.sleep(0.3)
    assert len(demo_box.steer.reports()) <= quiet + 1, "nothing shown again until it moves"
    page.mouse.move(middle[0], middle[1] + 3)
    demo_box.wait_for(lambda: len(demo_box.steer.reports()) > quiet + 1)
    page.wait_for_selector('#demo-pane[data-steer="steering"]', state="attached")
    assert len(demo_box.steer.releases()) == 1


def test_a_report_not_delivered_is_said_quietly_and_reports_go_on(demo_box):
    """Task 8's carried (a): a report answered 504 *not delivered* -- no rig on the gaze endpoint;
    before the whole-build review's M1, every report between runs and while paused -- is said
    quietly, never as an error; the page keeps sending, and steers again the moment one is
    taken."""
    page = demo_box.page
    page.goto(demo_box.url)
    demo_box.demo()
    page.wait_for_selector(_DRAWN, state="attached")
    screen = _box_of(page, "#demo-drawing svg")
    page.mouse.move(screen["x"] + screen["width"] / 2, screen["y"] + screen["height"] / 2)
    page.wait_for_selector('#demo-pane[data-steer="steering"]', state="attached")

    demo_box.steer.answer = serve.not_delivered(serve.GAZE_NOT_TAKEN)
    page.wait_for_selector('#demo-pane[data-steer="waiting"]', state="attached")
    tone = page.get_attribute("#demo-steer", "class")
    assert "crit" not in tone and "warn" not in tone
    assert "not reading the pointer now" in page.inner_text("#demo-steer")
    count = len(demo_box.steer.reports())
    demo_box.wait_for(lambda: len(demo_box.steer.reports()) >= count + 3)
    demo_box.steer.answer = (200, {"status": "sent", "said": serve.GAZE_SENT})
    page.wait_for_selector('#demo-pane[data-steer="steering"]', state="attached")


def test_a_viewer_who_cannot_write_sees_the_drawing_and_no_dot_and_one_signed_in_steers(gaze_rig):
    """§4.5: the https page not signed in sees the demo's drawing and no dot, and sends nothing;
    signed in, the dot is drawn where the pointer is and its reports reach the steer, past the
    token check `/gaze` shares with `/commands`."""
    page = gaze_rig.browser_page()
    gaze_rig.hub.offer(frame(demo=True, service=True, session_id=DEMO_SESSION))
    gaze_rig.hub.offer_drawn(_screen())
    page.wait_for_selector(_DRAWN, state="attached")
    screen = _box_of(page, "#demo-drawing svg")
    page.mouse.move(screen["x"] + screen["width"] / 2, screen["y"] + screen["height"] / 2)
    time.sleep(0.4)
    assert page.get_attribute("#demo-dot", "hidden") is not None
    assert gaze_rig.steer.seen == []

    _sign_in(page)
    page.wait_for_selector(_DRAWN, state="attached")
    screen = _box_of(page, "#demo-drawing svg")
    page.mouse.move(screen["x"] + screen["width"] / 2, screen["y"] + screen["height"] / 2)
    gaze_rig.wait_for(lambda: len(gaze_rig.steer.reports()) >= 2)
    page.wait_for_selector("#demo-dot:not([hidden])", state="attached")
    assert gaze_rig.steer.reports()[-1].over is True


def test_the_demo_screen_shows_only_this_sessions_drawing_and_goes_with_the_demo(demo_box):
    """Task 8's carried (c): the hub keeps the last drawing after a demo ends; the page shows the
    demo screen only while the frame says demo, and only the drawing of the session the frame is,
    so a drawing kept from an earlier demo never stands for the next."""
    page = demo_box.page
    page.goto(demo_box.url + "#demo")
    assert page.is_hidden("#demo-pane") and page.is_visible("#replica-pane")
    demo_box.demo()
    page.wait_for_selector(_DRAWN, state="attached")
    assert page.is_visible("#demo-pane.full") and page.is_hidden("#replica-pane")
    assert page.inner_text("#demo-tag") == "DEMO"

    demo_box.hub.offer(frame(demo=True, service=True, session_id="demo-20261114-130000"))
    page.wait_for_selector("#demo-none:not([hidden])", state="attached")
    assert page.is_hidden("#demo-drawing")
    demo_box.hub.offer(frame())
    page.wait_for_selector("#demo-pane[hidden]", state="attached")
    assert page.is_visible("#replica-pane") and page.inner_text("#demo-tag") == ""
    assert page.evaluate("document.body.classList.contains('demo-full')") is False


def test_a_demo_services_dialog_fills_now_offers_reference_and_opens_a_demo(demo_box):
    """§4.1: on a demo service *New session* offers `REFERENCE` alone, fills *←cage at* with the
    clock's minute and the id with `demo-YYYYMMDD-HHMMSS`, both editable, and the open sends
    `demo`."""
    page = demo_box.page
    demo_box.hub.offer(idle(demo=True, gaze=True, animals=("REFERENCE",)))
    page.goto(demo_box.url)
    before = time.time()
    page.click('[data-cmd="new"]')
    left, given = page.input_value("#dn-left"), page.input_value("#dn-id")
    after = time.time()
    minutes = {time.strftime("%H:%M", time.localtime(at)) for at in (before, after)}
    assert left in minutes, (left, minutes)
    assert re.fullmatch(r"demo-\d{8}-\d{6}", given), given
    stamps = {time.strftime("demo-%Y%m%d-%H%M%S", time.localtime(at))
              for at in range(math.floor(before), math.ceil(after) + 1)}
    assert given in stamps
    assert page.input_value("#dn-subject") == "REFERENCE"
    # Edited, a fill is the person's: the dialog reopened keeps it, and refills one cleared.
    page.fill("#dn-id", given + "b")
    page.fill("#dn-left", "")
    page.click("#dn-cancel")
    page.click('[data-cmd="new"]')
    assert page.input_value("#dn-id") == given + "b"
    left = page.input_value("#dn-left")
    assert left in {time.strftime("%H:%M", time.localtime(at)) for at in (before, time.time())}
    page.select_option("#dn-deployment", "rig_fixed")
    page.select_option("#dn-kind", "training")
    page.click("#dn-ok")
    demo_box.wait_for(lambda: _opens(demo_box))
    (opened,) = _opens(demo_box)
    assert (opened.demo, opened.animal, opened.session_id, opened.departure) == (
        True, "REFERENCE", given + "b", left)


def test_the_rig_pages_demo_box_locks_reference_fills_now_and_opens_a_demo(demo_box):
    """§4.1 on a live rig: where the idle frame says `gaze` and offers `REFERENCE`, the demo box
    locks the subject to `REFERENCE` and fills the departure and id; unticked, the subject is the
    person's again and the fills go; the open sends `demo`. Grayed with its reason where the frame
    says no gaze."""
    page = demo_box.page
    demo_box.hub.offer(idle(gaze=True, animals=("A", "REFERENCE")))
    page.goto(demo_box.url)
    page.click('[data-cmd="new"]')
    assert page.input_value("#dn-subject") == "" and page.input_value("#dn-id") == ""
    page.check("#dn-demo-box")
    assert page.input_value("#dn-subject") == "REFERENCE" and page.is_disabled("#dn-subject")
    assert re.fullmatch(r"demo-\d{8}-\d{6}", page.input_value("#dn-id"))
    assert re.fullmatch(r"\d{2}:\d{2}", page.input_value("#dn-left"))
    page.uncheck("#dn-demo-box")
    assert not page.is_disabled("#dn-subject")
    assert page.input_value("#dn-id") == "" and page.input_value("#dn-left") == ""
    page.check("#dn-demo-box")
    page.select_option("#dn-deployment", "rig_fixed")
    page.select_option("#dn-kind", "training")
    page.click("#dn-ok")
    demo_box.wait_for(lambda: _opens(demo_box))
    (opened,) = _opens(demo_box)
    assert (opened.demo, opened.animal) == (True, "REFERENCE")

    demo_box.hub.offer(idle(gaze=False, animals=("A", "REFERENCE")))
    page.wait_for_selector("#dn-demo-box[disabled]", state="attached")
    assert page.get_attribute("#dn-demo-box", "title") == web.NO_GAZE


# --- the pop-out, played with the mouse --------------------------------------------------------


class _LiveDemo:
    """**A demo, played in a real browser**: a demo service in process over the real link
    (`_demo.Demo`, its scripted pointer left out), `wlx serve` on its four endpoints, and the rig
    PC's own page at `#demo`, full-window; `register` is the suite's `zmq_cleanup`."""

    def __init__(self, tmp_path, launched, register) -> None:
        self.demo = Demo(tmp_path, None, register)
        link = self.demo.link
        self.server = Server(sub=link.pub_endpoint, req=link.rep_endpoint, http=("127.0.0.1", 0),
                             token=TOKEN, mark=link.mark_endpoint, gaze=link.gaze_endpoint)
        self._context = launched.new_context(viewport=WINDOW)
        self._context.add_init_script("window.localStorage.setItem('wlx-console-name', 'Box Op')")
        # When the page last sent a pointer report, for `flick`; the page itself is unchanged.
        self._context.add_init_script(
            "(() => { const sent = window.fetch; window.wlxGazeAt = 0;"
            " window.fetch = function (url) { if (url === '/gaze') {"
            " window.wlxGazeAt = performance.now(); } return sent.apply(this, arguments); }; })()")
        self.page = _Opening(self._context.new_page())
        self.page.set_default_timeout(WAIT_S * 1000)
        self.at: tuple[float, float] | None = None

    def __enter__(self) -> "_LiveDemo":
        self.demo.__enter__()
        self.server.start()
        self.page.goto(f"http://127.0.0.1:{self.server.address[1]}/#demo")
        return self

    def __exit__(self, *exc) -> None:
        try:
            self._context.close()
        finally:
            try:
                self.server.close()
            finally:
                self.demo.__exit__(*exc)

    def client(self, x_deg: float, y_deg: float) -> tuple[float, float]:
        """Where a position in degrees is in the window: the drawing's eye group's own transform,
        `D·tan` per axis, as the page reads a pointer back."""
        return tuple(self.page.evaluate(
            "([x, y]) => { const svg = document.querySelector('#demo-drawing svg');"
            " const eye = svg.querySelector('g.eye');"
            " const d = Number(eye.getAttribute('data-distance-cm'));"
            " const p = svg.createSVGPoint(); p.x = d * Math.tan(x * Math.PI / 180);"
            " p.y = d * Math.tan(y * Math.PI / 180);"
            " const c = p.matrixTransform(eye.getScreenCTM()); return [c.x, c.y]; }",
            [x_deg, y_deg]))

    def glide(self, x: float, y: float, seconds: float = GLIDE_S) -> None:
        """The mouse to client `(x, y)` along a hand's straight path taking `seconds` (`GLIDE_S`);
        at once with `seconds` 0."""
        x0, y0 = self.at if self.at is not None else (x, y)
        start = time.perf_counter()
        while True:
            share = 1.0 if seconds <= 0 else min(1.0, (time.perf_counter() - start) / seconds)
            self.page.mouse.move(x0 + (x - x0) * share, y0 + (y - y0) * share)
            if share >= 1.0:
                break
            time.sleep(GLIDE_STEP_S)
        self.at = (x, y)

    def look(self, at: tuple[float, float], seconds: float = GLIDE_S) -> None:
        self.glide(*self.client(*at), seconds=seconds)

    def flick(self, at: tuple[float, float]) -> None:
        """The mouse to `at`, degrees, in one move `FLICK_AFTER_S` after the page's next report."""
        x, y = self.client(*at)
        last = self.page.evaluate("window.wlxGazeAt")
        end = time.monotonic() + WAIT_S
        while self.page.evaluate("window.wlxGazeAt") == last:
            if time.monotonic() > end:
                pytest.fail("the page sent no pointer report")
            time.sleep(0.002)
        time.sleep(FLICK_AFTER_S)
        self.page.mouse.move(x, y)
        self.at = (x, y)

    def ready(self) -> None:
        """The session open, and the page steering its eye at `REST`: first a run of one trial,
        which waits for the page's pointer with the field drawn (demo mode's Task 10: before the
        first screen a page has nothing to point at), so the page puts its pointer on the field,
        which begins the trial, played at `REST` to its no fixation at its shortest wait; between
        runs the page keeps the eye, so the next run's first frame finds it live (Task 8's carried
        (a))."""
        self.demo.open()
        self.page.wait_for_selector("#demo-pane.full", state="attached")
        self.demo.start({**_QUICK, "fix_acquisition": 0.5}, trials=1)
        self.page.wait_for_selector(_DRAWN, state="attached")
        self.look(REST, seconds=0)
        self.page.wait_for_selector('#demo-pane[data-steer="steering"]', state="attached")
        self.demo.ended_run()

    def screen_with(self, wanted, what: str) -> Drawn:
        return self.demo.until(lambda f: isinstance(f, Drawn) and f.screen is not None
                               and wanted(f), what)

    def outcome(self) -> str:
        self.demo.ended_run()
        return self.demo.rows("trials.jsonl")[-1]["outcome"]


@pytest.fixture
def began(monkeypatch) -> list:
    """Each state the rig's world was told began, `(trial, state, frame)`, as the trial loop tells
    it (`run.World.began`): what the rig made of the pointer, seen without changing it."""
    told: list = []
    real = pointer.Pointing.began

    def spy(world, state, frame_):
        told.append((world.index, state, frame_))
        return real(world, state, frame_)

    monkeypatch.setattr(pointer.Pointing, "began", spy)
    return told


@pytest.fixture
def live(tmp_path, zmq_cleanup):
    with browser() as launched:
        with _LiveDemo(tmp_path, launched, zmq_cleanup) as made:
            yield made


def _states(began) -> tuple:
    return tuple(state for _, state, _ in began)


#: Every run here: no blank after an error, so the run ends on its outcome.
_QUICK = {"timeout": 0.0}


def test_the_popout_played_with_the_mouse_is_correct(live, began):
    """§9, played by hand: hold on the point, the ring appears, move to the odd one and stay. The
    rig's own eye rules score it correct, through the states a correct answer takes."""
    live.ready()
    began.clear()
    live.demo.start({**_QUICK, "fix_hold": 0.3, "target_hold": 0.2, "response_deadline": 3.0})
    live.screen_with(lambda f: "fix" in shown_names(f), "the fixation point")
    live.look(FIX)
    go = live.screen_with(lambda f: any(n.startswith("search.") for n in shown_names(f)),
                          "the ring")
    live.flick(target(go))

    assert live.outcome() == Outcome.CORRECT.value
    assert _states(began) == (*ANSWERED_STATES, "on_target")


def test_leaving_early_is_an_early_saccade(live, began):
    """§9, played by hand: on the point, then away before the go -- an early saccade, a fixation
    break."""
    live.ready()
    began.clear()
    live.demo.start({**_QUICK, "fix_hold": 2.0})
    live.screen_with(lambda f: "fix" in shown_names(f), "the fixation point")
    live.look(FIX)
    time.sleep(0.3)
    live.look(REST)

    assert live.outcome() == Outcome.FIXATION_BREAK.value
    assert _states(began) == (*FIXATED_STATES, "early")


def test_leaving_the_drawing_is_no_fixation(live, began):
    """§3.3: off the drawing is gaze away, never tracker loss: a page that steers and leaves the
    drawing keeps the eye, looking nowhere, and the trial ends on no fixation."""
    live.ready()
    began.clear()
    live.demo.start({**_QUICK, "fix_acquisition": 0.5})
    bar = _box_of(live.page, ".demo-bar")
    live.glide(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2)

    assert live.outcome() == Outcome.NO_FIXATION.value
    assert _states(began) == ("between", "await_fix")


def test_holding_b_is_tracker_lost(live, began):
    """§3.3: B held is tracker loss, which the trial ends on as its `tracker_lost` says."""
    live.ready()
    began.clear()
    live.demo.start({**_QUICK, "fix_hold": 2.0})
    live.screen_with(lambda f: "fix" in shown_names(f), "the fixation point")
    live.look(FIX)
    time.sleep(0.3)
    live.page.keyboard.down("b")
    try:
        assert live.outcome() == Outcome.TRACKER_LOST.value
    finally:
        live.page.keyboard.up("b")
    assert _states(began) == FIXATED_STATES


def test_switching_fix_hold_to_nonaging_sends_its_shortest_and_longest(rig):
    """The timing switch (the console settings design's §3; the PI, 2026-11-16): on the card of a
    timing setting held fixed, *drawn* opens its shapes; non-aging, its shortest and longest typed,
    and the box's Apply (since the console interface rework's Task 6; its drawn side's own *apply*
    is gone) sends a `form` of those two numbers, reaching the rig as the signed-in member's. A
    frame arriving meanwhile leaves the card on its drawn side, a draft. Through the wire, in a
    real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import ParamRow, SetForm, decode, encode

    rows = (ParamRow.of("fix_hold", "s", 0.05, 2.0, 0.3, False, (), "task", (), None, None,
                        "drawn"),)
    rig.hub.offer(decode(encode(frame(params=rows))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')

    page.click('[data-switch="drawn"][data-name="fix_hold"]')
    rig.hub.offer(decode(encode(frame(params=rows, trial_index=41))))
    page.select_option('select[data-shape="fix_hold"]', "non_aging")
    fields = '#params [data-fields="non_aging"]'
    page.fill(f'{fields} input[data-form="shortest"]', "0.75")
    page.fill(f'{fields} input[data-form="longest"]', "1.25")
    page.click('#params [data-apply="fix_hold"]')
    rig.wait_for(lambda: rig.dispatch.seen)

    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.shape, sent.numbers, sent.values, sent.weights,
            sent.by.name) == (SetForm, "fix_hold", "non_aging",
                              {"shortest": 0.75, "longest": 1.25}, (), (), "Jake Westerberg")


def test_scaling_disc_size_sends_its_factor(rig):
    """A size's switch (the console settings design's §5; the PI, 2026-11-16, "Size = factor x
    eccentricity"): on the card of a size held fixed, *scaled* opens its factor; typed, the box's
    Apply (since the console interface rework's Task 6) sends a `form` of shape `scaled` with that
    one number, reaching the rig as the signed-in member's. A frame arriving meanwhile leaves the
    card on its scaled side. Through the wire, in a real browser: run with `WLX_BROWSER=webkit`
    too, for Safari."""
    from wl_xcon.link import ParamRow, SetForm, decode, encode

    rows = (ParamRow.of("disc_size", "deg", 0.0, None, 1.0, False, (), "task", (), None, None,
                        "scaled"),)
    rig.hub.offer(decode(encode(frame(params=rows))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')

    page.click('[data-switch="scaled"][data-name="disc_size"]')
    rig.hub.offer(decode(encode(frame(params=rows, trial_index=41))))
    assert page.is_visible('#params [data-fields="scaled"] input[data-form="factor"]')
    page.fill('#params [data-fields="scaled"] input[data-form="factor"]', "0.3")
    page.click('#params [data-apply="disc_size"]')
    rig.wait_for(lambda: rig.dispatch.seen)

    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.shape, sent.numbers, sent.values, sent.weights,
            sent.by.name) == (SetForm, "disc_size", "scaled", {"factor": 0.3}, (), (),
                              "Jake Westerberg")


def test_picking_a_hue_swatch_sends_color(rig):
    """A color setting's card (the console settings design's §6; the PI, 2026-11-16, "you select a
    set, and then you have hue options from the set"): pressing a hue's swatch is a draft, the
    swatch pressed and nothing sent (the console interface design's call: "a swatch or a tick is a
    draft"), and the box's Apply sends a `color` of its set and hue, reaching the rig as the
    signed-in member's; a frame arriving meanwhile leaves the box as it was. Rewritten for the
    rework's Task 6: the swatch sent on its click before. Through the wire, in a real browser: run
    with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import ParamRow, SetColor, decode, encode

    color = {
        "sets": {"isohue": {"apex": [0.31272, 0.329], "luminance_cd_m2": 15.0, "design": None,
                            "hues": {"green": {"xy": [0.31324, 0.50711], "srgb": "#4a9a3e"},
                                     "red": {"xy": [0.45955, 0.32918], "srgb": "#c76f6a"}}}},
        "set": "isohue", "hue": "green", "approximate": True,
        "saturation": {"setting": None, "value": 1.0, "cd_m2": 15.0},
        "luminance": {"setting": None, "value": 15.0, "cd_m2": 15.0, "set_wide": False},
    }
    rows = (ParamRow.of("distractor_appearance", "appearance", None, None, None, False,
                        source="run", color=color),)
    rig.hub.offer(decode(encode(frame(params=rows))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')

    page.select_option('select[data-colorset="distractor_appearance"]', "isohue")
    page.click('#params .hue[data-name="distractor_appearance"][data-color="red"]')
    rig.hub.offer(decode(encode(frame(params=rows, trial_index=41))))
    _arrived(page, 41)
    assert rig.dispatch.seen == [] and _say(page, "distractor_appearance") == "not sent"
    assert page.get_attribute('#params .hue[data-color="red"]', "aria-pressed") == "true"
    page.click('#params [data-apply="distractor_appearance"]')
    rig.wait_for(lambda: rig.dispatch.seen)

    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.colorset, sent.color, sent.by.name) == (
        SetColor, "distractor_appearance", "isohue", "red", "Jake Westerberg")


def _looks_row(look=None, **fields):
    """The fixation point's look as the rig makes its row (`ParamRow.of`): a disc, a ring or a
    square of one gray, `look` the one in force (the disc by default), its choices their words."""
    from wl_xcon.link import ParamRow
    from wl_xcon.task import Annulus, P, Square

    gray = Gray(P("fix_luminance"))
    looks = (Disc(size=0.3, color=gray), Annulus(inner=0.15, outer=0.3, color=gray),
             Square(size=0.3, color=gray))
    row = ParamRow.of("fix_look", "appearance", None, None, looks[0] if look is None else look,
                      False, choices=looks, source="task", section="Stimuli")
    return dataclasses.replace(row, **fields), looks


def test_a_looks_shape_is_picked_on_its_box_and_applied(rig):
    """The pop-out revision's design §2 (a look's shape is "a setting on the console"; its plan's
    Task 5b): a setting whose choices are looks, none a color-set light, shows them as segments,
    each saying its kind and its words whole in its title, the one in force pressed. Pressing the
    square is a draft, as a swatch is -- nothing sent, a frame arriving meanwhile leaving it, the
    summary line "in force → the square", **each said as its segment says it** ("Disc → Square",
    the words whole in the line's title; the pop-out revision's Amendments, item 6: a look's words
    run too long for a line) -- and the box's Apply sends a `choice` of the square's words as the
    signed-in member's; the box then waits, its line "Disc → Square" again, and is in force with
    the square pressed. The ring pressed and a hold typed ride one Apply all, and *withdraw* takes
    the act back. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, ApplyMany, SetChoice, Staged, Withdraw

    jake = Box("Jake Westerberg")
    row, looks = _looks_row()
    disc, ring, square = row.choices
    page = _task6_page(rig, params=_task6_rows() + (row,))
    _open(page, "fix_look")
    segments = f'{_b("fix_look")} [data-choices="fix_look"] .ch'
    assert page.eval_on_selector_all(segments, "(all) => all.map((one) => [one.textContent, "
                                     "one.parentElement.title, one.getAttribute('aria-pressed')])"
                                     ) == [
        ["Disc", disc, "true"], ["Ring", ring, "false"], ["Square", square, "false"]]

    page.click(f'{segments}[data-choice="{square}"]')
    _offer(rig, 41, params=_task6_rows() + (row,))
    _arrived(page, 41)
    assert rig.dispatch.seen == [] and _say(page, "fix_look") == "not sent"
    assert page.get_attribute(f'{segments}[data-choice="{square}"]', "aria-pressed") == "true"
    mark, said, title = _marked(page, "fix_look")
    assert (mark, said) == ("●", "Disc → Square"), (mark, said)
    assert disc in title, title
    page.click(f'{_b("fix_look")} [data-apply]')
    rig.wait_for(lambda: rig.dispatch.seen)

    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.choice, sent.by.name) == (
        SetChoice, "fix_look", square, "Jake Westerberg")
    _offer(rig, 42, params=_task6_rows() + (row,),
           staged=(Staged("fix_look", disc, square, jake, False, cid=sent.cid),))
    _says(rig, page, "fix_look", "waiting · you")
    assert _marked(page, "fix_look")[:2] == ("◷", "Disc → Square")
    held, _ = _looks_row(looks[2], applied=Applied(43, str(jake)))
    _offer(rig, 43, params=_task6_rows() + (held,))
    _says(rig, page, "fix_look", "in force from trial 43")
    assert page.get_attribute(f'{segments}[data-choice="{square}"]', "aria-pressed") == "true"
    assert "draft" not in _classes(page, "fix_look")

    page.click(f'{segments}[data-choice="{ring}"]')
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    page.click("#drafts-apply")
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    together = rig.dispatch.seen[-1]
    assert type(together) is ApplyMany
    assert sorted((type(change).__name__, change.name) for change in together.changes) == [
        ("SetChoice", "fix_look"), ("SetParameter", "fix_hold")]
    (picked,) = [change for change in together.changes if isinstance(change, SetChoice)]
    assert picked.choice == ring
    _offer(rig, 44, params=_task6_rows() + (held,),
           staged=(Staged("fix_look", square, ring, jake, False, cid=together.cid),
                   Staged("fix_hold", 0.3, 0.5, jake, False, cid=together.cid)))
    _says(rig, page, "fix_look", "waiting · you")
    page.click(f'{_b("fix_look")} [data-withdraw="{together.cid}"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 3)
    assert (type(rig.dispatch.seen[-1]), rig.dispatch.seen[-1].cid) == (Withdraw, together.cid)


def test_a_choice_in_a_group_box_follows_the_frame_and_rides_its_apply(rig):
    """A setting's segments in a group's box (the console interface design's goal 8), its sentence
    with the segments in their place: a hold's luminance typed is a draft, and a frame that moves
    the look in force -- another person's change -- moves the segment pressed with it, the box kept
    for the draft (`follow`), so no look the rig no longer holds becomes a draft of its own; the
    ring pressed then rides the box's one Apply with the luminance, one `apply_many`. In a real
    browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import Applied, ApplyMany, GroupRow, ParamRow, SetChoice, SetParameter

    def rows(look=None, **fields):
        shown, looks = _looks_row(look, group="Fixation point", **fields)
        luminance = ParamRow.of("fix_luminance", "cd/m2", 0.0, 80.0, 40.0, False, source="task",
                                step=0.5, group="Fixation point", section="Stimuli")
        return _task6_rows() + (shown, luminance), looks

    groups = (GroupRow("Fixation point", ("fix_look", "fix_luminance"),
                       "The point is {fix_look} at {fix_luminance} cd/m²", "Stimuli"),)
    first, looks = rows()
    page = _task6_page(rig, params=first, groups=groups)
    _open(page, "Fixation point")
    box = _b("Fixation point")
    disc, ring, square = next(row for row in first if row.name == "fix_look").choices
    segment = f'{box} [data-choices="fix_look"] .ch'

    page.fill(f'{box} input[data-param="fix_luminance"]', "30")
    moved, _ = rows(looks[2], source="person", changed=True, applied=Applied(42, "kim"))
    _offer(rig, 42, params=moved, groups=groups)
    _arrived(page, 42)
    _until(page, "document.querySelector('" + box + " [data-choices=\"fix_look\"] .ch.on')"
                 ".getAttribute('data-choice').indexOf('Square') === 0")
    assert page.input_value(f'{box} input[data-param="fix_luminance"]') == "30"
    page.click(f'{segment}[data-choice="{ring}"]')
    page.click(f'{box} [data-apply]')
    rig.wait_for(lambda: rig.dispatch.seen)

    (sent,) = rig.dispatch.seen
    assert type(sent) is ApplyMany
    assert sorted((type(change).__name__, change.name, getattr(change, "choice", None) or
                   getattr(change, "value", None)) for change in sent.changes) == [
        (SetChoice.__name__, "fix_look", ring), (SetParameter.__name__, "fix_luminance", 30)]


def test_defining_a_color_by_hue_angle_previews_and_saves(rig):
    """A section's New color… panel (the console settings design's §6; the PI, 2026-11-16: "1,2,or
    3. you select an option and then enter the info", "Saved into a color set file"): by hue angle,
    290°, named violet, into the card's set, a frame arriving meanwhile; *preview* shows what `wlx
    serve` answers for it (`GET /color-preview`), its swatch and its sentence, and *save as a
    proposal* sends a `define_color` of those numbers as the signed-in member's. The panel says
    where it goes. Rewritten for the console interface rework's Task 7: the panel was each color
    card's own, keyed by its setting; it is now its section's one (the design's call), keyed by the
    section, here Other, the card's row naming none. Through the wire, in a real browser: run with
    `WLX_BROWSER=webkit` too, for Safari."""
    from pathlib import Path

    from wl_xcon.link import DefineColor, ParamRow, decode, encode
    from wl_xcon.photometry import ColorSet
    from wl_xcon.serve import color_preview
    from wl_xcon.web import NEW_COLOR_SAVED

    isohue = ColorSet.load(Path(__file__).parent / "fixtures" / "isohue_design.json")
    color = {
        "sets": {"isohue": {"apex": list(isohue.apex), "luminance_cd_m2": 15.0,
                            "design": dict(isohue.design),
                            "hues": {hue: {"xy": list(xy), "srgb": "#808080"}
                                     for hue, xy in isohue.colors.items()}}},
        "set": "isohue", "hue": "green", "approximate": True,
        "saturation": {"setting": None, "value": 1.0, "cd_m2": 15.0},
        "luminance": {"setting": None, "value": 15.0, "cd_m2": 15.0, "set_wide": False},
    }
    rows = (ParamRow.of("distractor_appearance", "appearance", None, None, None, False,
                        source="run", color=color),)
    rig.hub.offer(decode(encode(frame(params=rows))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    panel = '[data-newc="Other"]'
    _open(page, "new-color:Other")
    assert page.evaluate("document.querySelector('[data-newc=\"Other\"]').open")
    page.fill(f'{panel} [data-newc-fields="hue_angle"] input[data-newc-num="hue_deg"]', "290")
    page.fill(f"{panel} input[data-newc-name]", "violet")
    assert page.inner_text(f"{panel} .src") == f"{NEW_COLOR_SAVED[0]}isohue{NEW_COLOR_SAVED[1]}"
    rig.hub.offer(decode(encode(frame(params=rows, trial_index=41))))

    page.click(f'{panel} [data-cmd="preview_color"]')
    _, expected = color_preview(rig.hub.snapshot(on_box=False, stale_after_s=5.0)[0],
                                {"set": ["isohue"], "method": ["hue_angle"], "hue_deg": ["290"]})
    page.wait_for_function(
        "said => (document.querySelector('[data-newc=\"Other\"] .newc-out') || "
        "{}).textContent.trim() === said", arg=expected["said"])
    shown = page.eval_on_selector(f"{panel} .newc-out .chip", "chip => chip.style.background")
    rgb = tuple(int(expected["srgb"][i:i + 2], 16) for i in (1, 3, 5))
    assert shown in (expected["srgb"], "rgb({}, {}, {})".format(*rgb)), shown
    assert expected["in_srgb"] is True and expected["x"] is not None
    page.click(f'{panel} [data-cmd="define_color"]')
    rig.wait_for(lambda: rig.dispatch.seen)

    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.colorset, sent.new_set, sent.name, sent.method, dict(sent.numbers),
            sent.by.name) == (DefineColor, "isohue", False, "violet", "hue_angle",
                              {"hue_deg": 290.0}, "Jake Westerberg")


def _sectioned(rig, task="tasks/fixation_detection.py", **over):
    """A frame whose cards sit in three sections: Timing, Gaze windows and, nested under Stimuli,
    the fixation point; offered to the rig, through the wire."""
    from wl_xcon.link import ParamRow, decode, encode

    rows = (
        ParamRow.of("fix_hold", "s", 0.1, 1.0, 0.3, False, section="Timing"),
        ParamRow.of("fix_window", "deg", 0.0, 9.0, 2.0, False, section="Gaze windows",
                    changed=True),
        ParamRow.of("fix_size", "deg", 0.0, 9.0, 0.5, False, section="Stimuli/fixation point"),
    )
    rig.hub.offer(decode(encode(frame(params=rows, task=task, **over))))


def _open(page, name: str, root: str = "#params") -> None:
    """**Open setting `name` in its tab's editor** as a person does, by a click on its summary
    line (the summary and editor design of 2026-11-19)."""
    page.click(f'{root} > .summary .line[data-open="{name}"]')


def _opened(page, root: str = "#params") -> list:
    """What the editor of `root` shows: each box's or panel's name not hidden, or the
    placeholder's words."""
    return page.evaluate("""(root) => { const editor = document.querySelector(root + ' > .editing');
        return editor === null ? null : Array.from(editor.children).filter((child) => !child.hidden)
        .map((child) => child.getAttribute('data-card') || child.getAttribute('data-newc') ||
        child.textContent.trim()); }""", root)


def test_a_store_that_throws_still_opens_a_setting(rig):
    """The summary and editor design's goal 5, with the browser's store failing -- a private
    window, blocked site data -- on every read and write before the page runs: a click still opens
    a setting and a frame keeps it opened, for as long as the page is shown; a reload shows the
    placeholder; nothing is raised into the page. Replaces `test_a_store_that_throws_leaves_every_
    section_open`: the sections no longer fold. In a real browser: run with `WLX_BROWSER=webkit`
    too, for Safari."""
    _sectioned(rig)
    page = rig.browser_page()
    page.add_init_script(
        "const boom = () => { throw new Error('storage is blocked'); };"
        "Storage.prototype.getItem = boom; Storage.prototype.setItem = boom;"
        "Storage.prototype.removeItem = boom;")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.reload()
    page.click('label[for="t-task"]')

    assert _opened(page) == ["click a setting above to change it"]
    _open(page, "fix_window")
    assert _opened(page) == ["fix_window"]
    _sectioned(rig, trial_index=41)
    _until(page, "document.querySelector('#params .summary') !== null")
    page.wait_for_timeout(300)  # housekeeping: past the frame's patch
    assert _opened(page) == ["fix_window"]
    page.reload()
    page.click('label[for="t-task"]')

    assert _opened(page) == ["click a setting above to change it"]
    assert not [e for e in errors if "storage is blocked" in e], errors


def _training_rows(gain, step=0.1):
    """A Training tab's cards: a bar a person holds (*hand back* live on it), the run's gain, and
    a stage's step in a section nested under Training, so a frame can change each."""
    from wl_xcon.link import ParamRow

    return tuple(dataclasses.replace(row, section=section) for row, section in (
        (ParamRow("move_up_bar", "fraction", 0.5, 1.0, 0.9, False, None, "person", ("near",)),
         "Training"),
        (ParamRow("gain", "", None, None, gain, False, None, "run"), "Training"),
        (ParamRow.of("fade_in_step", "fraction", 0.05, 1.0, step, False), "Training/Fade-in"),
    ))


def test_a_press_on_a_training_card_is_not_lost_when_a_frame_lands_under_it(rig):
    """The whole-build review's I3: the Training tab's cards are held while a pointer is down
    inside them, as the Task parameters tab's are (fix round 2 of the C3 plan's Task 18), so a
    frame that changes them mid-press does not replace *hand back* under the mouse -- WebKit never
    focuses a clicked button. The press arrives, and the frame held under it is shown once it is
    up. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import HandBack

    _offer(rig, 40, params=_training_rows(2.0))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-training"]')
    _more(page, "#training-params")

    page.hover('#training-params [data-cmd="hand_back"][data-name="move_up_bar"]')
    page.mouse.down()
    _offer(rig, 41, params=_training_rows(3.0))
    _arrived(page, 41)
    assert "2.00" in page.text_content("#training-params")  # held under the press
    page.mouse.up()
    rig.wait_for(lambda: len(rig.dispatch.seen) == 1)
    rig.wait_for(lambda: "3.00" in page.text_content("#training-params"))

    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.by.name) == (HandBack, "move_up_bar", "Jake Westerberg")


def test_the_training_tabs_opened_setting_is_kept_under_its_own_key(rig):
    """The summary and editor design's goal 5 on the Training tab: the setting opened in its
    editor stays opened across a frame that changes its boxes and across a reload, kept for its
    task under the Training tab's own key, `wlx.training-opened.<task>`; the Task parameters tab's
    is not touched. Replaces `test_a_collapsed_training_section_stays_collapsed_across_a_frame`:
    the sections no longer fold. In a real browser: run with `WLX_BROWSER=webkit` too, for
    Safari."""
    _offer(rig, 40, params=_training_rows(2.0))
    page = rig.browser_page()
    page.click('label[for="t-training"]')
    assert _opened(page, "#training-params") == ["click a setting above to change it"]

    _open(page, "fade_in_step", "#training-params")
    assert _opened(page, "#training-params") == ["fade_in_step"]
    _offer(rig, 41, params=_training_rows(2.0, step=0.3))
    _arrived(page, 41)
    _until(page, "document.querySelector('#training-params').textContent.indexOf('0.30') !== -1")

    assert _opened(page, "#training-params") == ["fade_in_step"]
    assert page.evaluate("window.localStorage.getItem('wlx.training-opened.tasks/"
                         "fixation_detection.py')") == "fade_in_step"
    assert page.evaluate("window.localStorage.getItem('wlx.opened.tasks/"
                         "fixation_detection.py')") is None
    page.reload()
    page.click('label[for="t-training"]')
    assert _opened(page, "#training-params") == ["fade_in_step"]
    assert page.get_attribute('#training-params .line[data-open="fade_in_step"]',
                              "aria-pressed") == "true"


# --- the console interface rework's Task 5: the box, drawn (the design of 2026-11-19) ----------

#: The widths a trainer's laptop gives the page (the design's "How it is judged done": "no text
#: past a box at 1024, 1280 and 1440 wide"), each at a laptop's height.
WIDTHS = (1024, 1280, 1440)
LAPTOP_H = 800

#: A refusal as long as the one the layout review found on `fix_hold` (about 100 words), so a box
#: holding one is measured.
_LONG_WHY = ("'fix_hold' at 30 is refused, and the previous value stands: the trial ends "
             "NO_FIXATION after 10 s, while the hold can take up to 30 s, so some trials could "
             "never be answered, and an animal held that long learns nothing from the trial it "
             "cannot finish; shorten the hold, or lengthen the timeout so that the longest hold "
             "and the time to acquire the point both fit inside it, then apply again (XC-343)")


def _popout_session(tmp_path):
    """**The pop-out search's session** as `_popout_frame` and `_popout_own` read it: its rows
    (`Session.parameters`) and its groups (`Session.groups`), schema 23."""
    from wl_xcon.dio import Simulated as Card
    from wl_xcon.taskd import Session, SessionSpec
    from wl_xcon.welfare import Deployment, Simulated as Pump

    import _sessions
    from _demo import ALLOCATION, POPOUT, xtasks_or_skip

    spec = SessionSpec(
        task=str(xtasks_or_skip() / POPOUT), allocation=ALLOCATION, root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=1, frame_period=1 / 240, seed=1,
        values={"pairings": 66}, bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB, plan="training")
    return Session(spec, card=Card(), pump=Pump())


def _popout_own(tmp_path, **over):
    """**The pop-out search's own rows and groups, as its session makes them** (the ledger's ruling
    for the summary and editor build's Task 3: "a new test on the wl-xtasks pop-out's own rows"):
    nothing changed in them -- no long plain name, no staged change -- but a setting that holds no
    value yet shown at its task's start (`Param.start`), as a run shows it."""
    import importlib.util

    from wl_xcon.link import GroupRow, ParamRow
    from _demo import POPOUT, xtasks_or_skip

    session = _popout_session(tmp_path)
    spec = importlib.util.spec_from_file_location("popout_own", xtasks_or_skip() / POPOUT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    starts = {param.name: param.start for param in module.TASK.params}
    rows = tuple(ParamRow.of(*row) for row in session.parameters)
    rows = tuple(dataclasses.replace(row, value=starts[row.name])
                 if row.value is None and isinstance(starts.get(row.name), (int, float)) else row
                 for row in rows)
    return frame(params=rows, groups=tuple(GroupRow(*group) for group in session.groups),
                 task="tasks/popout_search.py", **over)


def _popout_frame(tmp_path, **over):
    """**The pop-out search's own settings as its session makes their rows** (`Session.parameters`,
    schema 23; the PI's try-out task), with the states a box must hold without overrunning: a plain
    name of the longest a task may declare (`task.LABEL_LIMIT`), `fix_hold` drawn by a person with
    its profile, a size scaled, a value over a draw with its live numbers, a change staged, the
    long refusal (`_LONG_WHY`), and a change in force with a warning; the color boxes as the rig
    makes them."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, ParamRow, Refused, Staged
    from wl_xcon.task import LABEL_LIMIT, NonAging
    from wl_xcon.variation import profile

    rows = {row[0]: ParamRow.of(*row) for row in _popout_session(tmp_path).parameters}
    shape = {"shape": "non_aging", "numbers": {"shortest": 0.5, "longest": 1.25},
             "values": [], "weights": [], "by": "person"}
    drawn = profile(NonAging(minimum=0.5, mean=0.25, maximum=1.25)).as_dict()
    rows["fix_hold"] = dataclasses.replace(
        rows["fix_hold"], label="Fixation hold, before the array is shown"[:LABEL_LIMIT],
        source="form", switch="drawn", shape=shape, profile=drawn,
        help="How long gaze must stay on the fixation point before the array appears.")
    rows["fix_acquisition"] = dataclasses.replace(
        rows["fix_acquisition"], source="range", draw="uniform from 1 to 3.5 s, changed live",
        numbers={"low": 1.0, "high": 3.5}, conditions=("near", "far", "middle"), more=4)
    rows["disc_size"] = dataclasses.replace(rows["disc_size"], source="task", switch="scaled")
    rows["set_size"] = dataclasses.replace(
        rows["set_size"], applied=Applied(39, "jake (box, unverified)"),
        warned=("crowded-array: 12 objects on a 6° ring leave 1.1° between windows of 1.6°",))
    by = Box("Jake Westerberg")
    return frame(params=tuple(rows.values()), task="tasks/popout_search.py",
                 staged=(Staged("fix_window", 2.0, 1.5, by, False, cid="box-2"),),
                 refusals=(Refused("fix_hold", by, _LONG_WHY, cid="box-1", value=30.0),),
                 **over)


#: **What passes a box's edge, measured** (the layout review's finding 1: "this bug is invisible
#: to a test that reads the HTML"): for every box on the shown tab, each descendant whose right
#: edge passes the box's, and each whose own content is wider than it is. A text cut short on
#: purpose -- `text-overflow: ellipsis` over `overflow: hidden` -- is excepted only where its
#: `title` holds it whole, and so is what it holds, which it clips; a field, whose text scrolls
#: inside it, is excepted from the second; and what a closed `<details>` holds, which is not shown
#: (both engines still lay it out). Each found as `name: tag.class (why)`.
_OVERRUNS = """(root) => {
  const found = [];
  const cut = (node) => {
    const style = getComputedStyle(node);
    return style.textOverflow === 'ellipsis' && style.overflowX === 'hidden' &&
      Boolean(node.getAttribute('title'));
  };
  const clipped = (node, box) => {
    for (let at = node.parentElement; at && at !== box; at = at.parentElement) {
      if (cut(at)) { return true; }
      if (at.tagName === 'DETAILS' && !at.open && node.closest('summary') === null) { return true; }
    }
    return false;
  };
  for (const box of document.querySelectorAll(root + ' .box')) {
    const edge = box.getBoundingClientRect().right;
    for (const node of box.querySelectorAll('*')) {
      const rect = node.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) { continue; }
      if (clipped(node, box)) { continue; }
      const said = box.getAttribute('data-card') + ': ' + node.tagName.toLowerCase() + '.' +
        (node.getAttribute('class') || '').split(' ').join('.');
      if (rect.right > edge + 0.5) { found.push(said + ' (right edge ' + Math.round(rect.right - edge) + ' px past)'); }
      if (node instanceof SVGElement || ['INPUT', 'SELECT', 'TEXTAREA'].includes(node.tagName)) { continue; }
      if (node.scrollWidth > node.clientWidth + 1 && node.clientWidth > 0 && !cut(node)) {
        found.push(said + ' (' + node.scrollWidth + ' px of content in ' + node.clientWidth + ')');
      }
    }
  }
  return found;
}"""


#: **What passes a summary line's edge, a section's or the summary's** (the summary and editor
#: design's "How it is judged done": "no text past its line or the editor's edge"): each line's
#: mark, name and value inside its line, each section's header inside its section and each
#: section inside the summary; a text cut short with an ellipsis is a line's design (its whole in
#: the line's `title`, the header's in its own), so it is found only where no title holds it; and
#: the page scrolling across.
_LINE_OVERRUNS = """(root) => {
  const found = [];
  const past = (inner, outer) => inner.right > outer.right + 0.5 || inner.left < outer.left - 0.5 ||
    inner.bottom > outer.bottom + 0.5 || inner.top < outer.top - 0.5;
  for (const line of document.querySelectorAll(root + ' > .summary .line')) {
    const edge = line.getBoundingClientRect();
    for (const part of line.children) {
      const rect = part.getBoundingClientRect();
      if (rect.width > 0 && past(rect, edge)) { found.push(line.getAttribute('data-open') + ': ' + part.className); }
      if (part.scrollWidth > part.clientWidth + 1 && !line.getAttribute('title')) {
        found.push(line.getAttribute('data-open') + ': ' + part.className + ' cut with no title');
      }
    }
  }
  const whole = document.querySelector(root + ' > .summary').getBoundingClientRect();
  for (const section of document.querySelectorAll(root + ' > .summary .ssec')) {
    const head = section.querySelector(':scope > h4') || section.querySelector(':scope > .skeep > h4');
    if (past(head.getBoundingClientRect(), section.getBoundingClientRect())) { found.push('header ' + head.textContent); }
    if (head.scrollWidth > head.clientWidth + 1 && !head.title) { found.push('header cut ' + head.textContent); }
    if (past(section.getBoundingClientRect(), whole)) { found.push('section ' + section.getAttribute('data-section')); }
  }
  if (document.documentElement.scrollWidth > window.innerWidth) { found.push('the page scrolls across'); }
  return found;
}"""

#: **What passes the editor's edge, or its box's, for every setting opened in turn**: each line
#: of the tab clicked (its own `click()`, so no pointer press holds a frame), then every shown
#: node in the editor whose right edge passes the editor's, and `_OVERRUNS` on the box shown.
_EDITOR_OVERRUNS = """(root) => {
  const overruns = """ + _OVERRUNS + """;
  const found = [];
  const editor = document.querySelector(root + ' > .editing');
  for (const line of document.querySelectorAll(root + ' > .summary .line[data-open]')) {
    line.click();
    const edge = editor.getBoundingClientRect().right;
    for (const node of editor.querySelectorAll('*')) {
      const rect = node.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) { continue; }
      const shut = node.parentElement && node.parentElement.closest('details:not([open])');
      if (shut && node.closest('summary') === null) { continue; }
      if (rect.right > edge + 0.5) {
        found.push(line.getAttribute('data-open') + ': ' + node.tagName.toLowerCase() + '.' +
          (node.getAttribute('class') || '') + ' past the editor by ' + Math.round(rect.right - edge));
      }
    }
    found.push(...overruns(root));
  }
  return found;
}"""


def test_no_text_passes_its_box_at_three_widths(rig, tmp_path):
    """The PI, trying the console in Safari (2026-11-19): "text overruns the boxes, eg, color
    section". At 1024, 1280 and 1440 wide, on the Task parameters and the Training tabs, no
    summary line's text passes its line (`_LINE_OVERRUNS`), and with each setting opened in turn
    no text passes the editor or its box (`_EDITOR_OVERRUNS`): not the color boxes, not the
    longest plain name, not the long refusal, not a drawn box's shapes; and again with every box's
    *more* and every New color panel open. Rewritten for the summary and editor design of
    2026-11-19 from the grid's boxes to the lines and the editor. Through the wire, in a real
    browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_frame(tmp_path))))
    page = rig.browser_page()
    for tab, root in (("t-task", "#params"), ("t-training", "#training-params")):
        page.click(f'label[for="{tab}"]')
        page.wait_for_selector(f"{root} .box", state="attached")
        assert page.locator(f"{root} > .summary .line").count() > 0, (tab, "the summary's lines")
        if root == "#params":
            assert page.locator("#params .box .clr").count() >= 2, "the color boxes are measured"
            # One for each section holding a color card: Colors, and the fixation point's since
            # the pop-out's revision gave its two looks their hues.
            assert page.locator("#params > .summary .line.newcolor").count() == 2
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": LAPTOP_H})
            assert page.evaluate(_LINE_OVERRUNS, root) == [], (tab, width)
            page.evaluate(f"document.querySelectorAll('{root} > .editing details')"
                          ".forEach((d) => {{ d.open = false; }})")
            assert page.evaluate(_EDITOR_OVERRUNS, root) == [], (tab, width, "closed")
            page.evaluate(f"document.querySelectorAll('{root} > .editing details')"
                          ".forEach((d) => {{ d.open = true; }})")
            assert page.evaluate(_EDITOR_OVERRUNS, root) == [], (tab, width, "open")
            assert page.evaluate(_LINE_OVERRUNS, root) == [], (tab, width, "after")


def test_an_open_more_stays_open_across_a_frame(rig):
    """The console interface rework's Task 5: a box's *more* a person opened stays open when a
    frame replaces the boxes (as a section does, `applySections`), and one they closed again stays
    closed; the frame's news shows in it. In a real browser: run with `WLX_BROWSER=webkit` too, for
    Safari."""
    from wl_xcon.link import ParamRow

    def rows(why):
        return (ParamRow.of("fix_hold", "s", 0.0, None, 0.5, False, why={"low": why}),
                ParamRow.of("timeout", "s", 0.0, None, 2.0, False))

    _offer(rig, 40, params=rows("below 0 cannot be"))
    page = rig.browser_page()
    page.click('label[for="t-task"]')
    _more(page)
    page.click('#params .box[data-card="timeout"] > details.more > summary')
    _offer(rig, 41, params=rows("a reason of trial 41"))
    _arrived(page, 41)
    # `text_content`: the editor shows one box, and `inner_text` reads no box it hides.
    rig.wait_for(lambda: "a reason of trial 41" in page.text_content("#params"))

    assert page.evaluate("[document.querySelector('#params .box[data-card=\"fix_hold\"] > "
                         "details.more').open, document.querySelector('#params "
                         ".box[data-card=\"timeout\"] > details.more').open]") == [True, False]


def test_the_first_setting_starts_within_260px_at_1280x800(rig, tmp_path):
    """The design's "How it is judged done": "the first setting within the first 260 px at 1280 ×
    800" (the layout review's finding 4: about 500 px went before it), which the summary and
    editor design makes the first summary line's (its call: "The 260 px rule becomes: the first
    summary line within 260 px of the top at 1280 × 800"). Measured from the top of the page,
    unscrolled, on the Task parameters tab: the one bar that stays in view (the console interface
    rework's Task 8) put the session's details behind *session*, so the tabs follow it."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_frame(tmp_path))))
    page = rig.browser_page()
    page.set_viewport_size({"width": 1280, "height": 800})
    page.click('label[for="t-task"]')
    page.wait_for_selector("#params .box", state="attached")
    assert page.locator("#params > .summary .line").count() > 0, "the summary's lines"

    top = page.evaluate("document.querySelector('#params > .summary .line').getBoundingClientRect()"
                        ".top + window.scrollY")
    assert top <= 260, top


def test_every_popout_line_is_above_the_fold_at_1280x800(rig, tmp_path):
    """The summary and editor design's goal 1: "all of the pop-out's Task parameters fit above
    the editor on a 1280 × 800 screen with the top bar", judged as its call says: the pop-out as
    built, at 1280 × 800 with the demo screen's column shown (as in the PI's try-out), no banner,
    the drafts bar at the window's foot (fixed, not in the flow; none here), the last summary
    line's bottom within 800 px, unscrolled. Through the wire, in a real browser: run with
    `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_frame(tmp_path, demo=True))))
    page = rig.browser_page()
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    page.click('label[for="t-task"]')
    page.wait_for_selector("#params .box", state="attached")
    assert page.locator("#params > .summary .line").count() > 0, "the summary's lines"
    assert page.is_visible("#demo-pane"), "the demo screen's column is shown"
    assert not page.is_visible("#stream") and not page.is_visible("#drafts")

    bottoms = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#params > .summary .line')).map((line) => [line.getAttribute('data-open'),
        line.getBoundingClientRect().bottom + window.scrollY])""")
    assert len(bottoms) >= 15, bottoms
    below = [(name, round(bottom)) for name, bottom in bottoms if bottom > LAPTOP_H]
    assert below == [], below
    # In columns (the design's goal 1): two at 1280 wide beside the demo screen, as wide as the
    # longest plain name a task may declare with its value (the ledger's ruling for the build's
    # Task 2, which the four of the design cut: `test_no_popout_name_is_cut_at_1280`).
    columns = page.evaluate("""() => new Set(Array.from(document.querySelectorAll(
        '#params > .summary > .ssec')).map((section) => Math.round(
        section.getBoundingClientRect().left))).size""")
    assert columns == 2, columns


#: **The special kinds' shares** (`popout_search.py`'s Special trials), by name.
SHARES = ("target_absent_percent", "odd_place_empty_percent", "distractor_alone_percent",
          "odd_one_alone_percent")


def _heads_kept(page, root: str = "#params") -> list:
    """Each section of subsections alone whose header stands in another column than its first
    subsection, or at a column's foot with nothing under it, by name: the header stranded."""
    return page.evaluate("""(root) => Array.from(document.querySelectorAll(
        root + ' > .summary > .ssec')).filter((section) => !section.querySelector(':scope > .line')
        && section.querySelector('.ssec')).filter((section) => {
          const head = section.querySelector(':scope > h4, :scope > .skeep > h4');
          const first = section.querySelector('.ssec');
          const h = head.getBoundingClientRect(), f = first.getBoundingClientRect();
          return Math.round(h.left) !== Math.round(f.left) || f.top < h.bottom - 1;
        }).map((section) => section.getAttribute('data-section'))""", root)


#: **The special trials' shares a test sets** (the PI, 2026-11-20, "Shorter line, no cut"): all at
#: 0, one at 10, two on, all at 10 and all at 100, each with the line it says.
SHARE_CASES = (
    ({}, "none"),
    ({"target_absent_percent": 10}, "absent 10%"),
    ({"target_absent_percent": 10, "odd_place_empty_percent": 5}, "absent 10% · empty 5%"),
    (dict.fromkeys(SHARES, 10), "4 kinds · 40% of trials"),
    (dict.fromkeys(SHARES, 100), "4 kinds · 400% of trials"),
)


@pytest.mark.parametrize("width", [1024, 1280, 1440])
def test_turning_special_trials_on_moves_nothing_in_the_summary(rig, tmp_path, width):
    """The pop-out revision's whole-build review, I1 (the summary and editor design's anti-goal:
    "the page jumping under the pointer"): **the summary's columns are sized from the widest value
    each setting can show** (`web._widest`), never from the values in force, and a group's line by
    its name. On the pop-out's own rows at 1024, 1280 and 1440 wide, 800 high, the demo screen's
    column shown, the four shares at 0, one at 10, two on, all at 10 and all at 100 move no line,
    no header, the legend nor the editor's top, and keep the columns; and **a section of subsections
    alone keeps its header with its first subsection** in its column (WebKit left "Stimuli · 16
    settings" alone at a column's foot). **And the Special trials line is never cut** (the PI,
    2026-11-20, from his try-out: "Shorter line, no cut"): it says only the shares that are on, in
    short words, "none" with every share at 0, or, where those would not fit, how many kinds and
    their sum -- its value never wider than its box (`scrollWidth <= clientWidth`) -- and its title
    holds every share whole. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import decode, encode

    made = _popout_own(tmp_path, demo=True)
    labels = {row.name: row.label for row in made.params if row.name in SHARES}

    def offer(shares, trial):
        rig.hub.offer(decode(encode(dataclasses.replace(made, trial_index=trial, params=tuple(
            dataclasses.replace(row, value=shares.get(row.name, 0)) if row.name in SHARES else row
            for row in made.params)))))

    offer({}, 40)
    page = rig.browser_page()
    page.set_viewport_size({"width": width, "height": LAPTOP_H})
    page.click('label[for="t-task"]')
    page.wait_for_selector("#params > .summary .line", state="visible")
    _arrived(page, 40)
    before = _rects(page)
    assert before[-1][0] == "editing", before[-1]
    assert _heads_kept(page) == []
    line = '#params > .summary .line[data-open="Special trials"]'
    for trial, (shares, said) in enumerate(SHARE_CASES, start=41):
        offer(shares, trial)
        _arrived(page, trial)
        page.wait_for_function(f"() => document.querySelector({line!r} + ' > .lv')"
                               f".textContent === {said!r}")
        assert _rects(page) == before, shares
        assert _heads_kept(page) == [], shares
        shown = page.evaluate(f"""() => {{ const lv = document.querySelector({line!r} + ' > .lv');
            return [lv.scrollWidth, lv.clientWidth]; }}""")
        assert shown[0] <= shown[1], (shares, said, shown)
        title = page.get_attribute(line, "title")
        for name, label in labels.items():
            assert f"{label} {shares.get(name, 0)}%" in title, (name, title)


def test_the_special_trials_line_says_the_rest_are_normal_search(rig, tmp_path):
    """The pop-out revision's plan, Amendments, item 4 (the console interface design's goal 8:
    "the remainder shown as "normal search""; the PI, 2026-11-19, "One box after Timing"): **the
    special trials are one box, its section right after Timing**, read as one sentence, and after
    it the trials it leaves normal -- "70 normal search" from the shares in force, as the rig
    renders it -- and while a draft is open, from the box's own fields as they are typed: "40
    normal search", "none normal search" at 100, and past 100 the warning's own words after it; a
    field emptied counts none, and Discard says the values in force again. Through the wire, in a
    real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon import web
    from wl_xcon.check import IN_PROPORTION
    from wl_xcon.link import decode, encode

    made = _popout_own(tmp_path)
    shares = {"target_absent_percent": 20, "odd_place_empty_percent": 10}
    made = dataclasses.replace(made, params=tuple(
        dataclasses.replace(row, value=shares[row.name]) if row.name in shares else row
        for row in made.params))
    rig.hub.offer(decode(encode(made)))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    page.wait_for_selector("#params > .summary .line", state="visible")
    sections = page.eval_on_selector_all("#params > .summary > .ssec", "(all) => all.map((one) => "
                                         "one.getAttribute('data-section'))")
    assert sections[:3] == ["Timing", "Special trials", "Gaze windows"], sections
    _open(page, "Special trials")
    box = _b("Special trials")
    rest = f"{box} > .editor > .gr"
    assert page.text_content(rest) == "70 normal search"
    assert web._rest_said(30) == "70 normal search"

    page.fill(f'{box} input[data-param="distractor_alone_percent"]', "30")
    assert page.text_content(rest) == "40 normal search"
    page.fill(f'{box} input[data-param="odd_one_alone_percent"]', "40")
    assert page.text_content(rest) == "none normal search" == web._rest_said(100)
    page.fill(f'{box} input[data-param="odd_one_alone_percent"]', "45")
    assert page.text_content(rest) == f"none normal search: {IN_PROPORTION}" == web._rest_said(105)
    page.fill(f'{box} input[data-param="odd_one_alone_percent"]', "")
    assert page.text_content(rest) == "40 normal search"
    page.click(f"{box} [data-discard]")
    page.wait_for_function(f"() => document.querySelector({rest!r}).textContent === "
                           f"'70 normal search'")


def _rects(page, root: str = "#params") -> list:
    """Where everything above the editor stands: each summary line, each section's header, the
    legend and the find box, in page coordinates."""
    return page.evaluate("""(root) => Array.from(document.querySelectorAll(
        root + ' > .summary .line, ' + root + ' > .summary .ssec > h4, ' + root +
        ' > .summary .skeep > h4, ' + root + ' > .legend, ' +
        root + ' > .editing')).map((node) => { const r = node.getBoundingClientRect();
        return [node.getAttribute('data-open') || node.className, Math.round(r.left * 10),
                Math.round((r.top + window.scrollY) * 10), Math.round(r.width * 10),
                Math.round(r.height * 10)]; })""", root)


def test_a_click_opens_a_setting_and_nothing_above_moves(rig, tmp_path):
    """The summary and editor design's goal 2 and its anti-goal ("the page jumping under the
    pointer: opening a setting changes nothing above the editor"): at 1280 × 800 the editor first
    says "click a setting above to change it"; a click on a summary line opens that setting's box
    there, alone, its line pressed; and opening three in turn -- a drawn hold with its long
    refusal, the pairings' grid, a whole count -- leaves every line, every header, the legend and
    the editor's top where they were. Through the wire, in a real browser: run with
    `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_frame(tmp_path))))
    page = rig.browser_page()
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    page.click('label[for="t-task"]')
    lines = page.locator("#params > .summary .line[data-open]")
    assert lines.count() == page.locator("#params > .editing > .box").count() + 2, (
        "a line for every box, and the New color… of Colors and of the fixation point")
    assert _opened(page) == ["click a setting above to change it"]
    before = _rects(page)
    editor_top = before[-1][2]
    heights = page.eval_on_selector_all(
        "#params > .summary .line", "lines => lines.map((line) => line.getBoundingClientRect().height)")
    assert len(set(heights)) == 1 and 18 <= heights[0] <= 22, heights

    for name in ("fix_hold", "pairings", "set_size"):
        _open(page, name)
        assert _opened(page) == [name], name
        pressed = page.eval_on_selector_all(
            "#params > .summary .line[aria-pressed='true']",
            "lines => lines.map((line) => line.getAttribute('data-open'))")
        assert pressed == [name], (name, pressed)
        after = _rects(page)
        assert after[:-1] == before[:-1], name
        assert after[-1][2] == editor_top, name
    assert page.is_visible(f'{_b("set_size")} input[data-param="set_size"]')
    assert rig.dispatch.seen == [], "opening a setting sends nothing"


def test_the_opened_setting_survives_a_frame_and_a_reload(rig):
    """The summary and editor design's goal 5: the setting opened stays opened across a frame that
    changes it, a tab switch and a reload, kept per task in the browser's own storage
    (`wlx.opened.<task>`); another task's settings open with nothing opened, and the first task's
    opens again on return. Replaces `test_sections_open_as_last_left_per_task`: the sections no
    longer fold. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    _sectioned(rig)
    page = rig.browser_page()
    page.click('label[for="t-task"]')
    assert _opened(page) == ["click a setting above to change it"]
    _open(page, "fix_window")
    assert _opened(page) == ["fix_window"]

    from wl_xcon.link import ParamRow, decode, encode
    rows = (ParamRow.of("fix_hold", "s", 0.1, 1.0, 0.3, False, section="Timing"),
            ParamRow.of("fix_window", "deg", 0.0, 9.0, 3.5, False, section="Gaze windows",
                        changed=True),
            ParamRow.of("fix_size", "deg", 0.0, 9.0, 0.5, False, section="Stimuli/fixation point"))
    line = '#params > .summary .line[data-open="fix_window"]'
    page.evaluate("(line) => { document.querySelector(line).wlxSame = true; }", line)
    rig.hub.offer(decode(encode(frame(params=rows, trial_index=41))))
    _until(page, "document.querySelector('#params input[data-param=\"fix_window\"]')"
                 ".value === '3.50'")
    assert _opened(page) == ["fix_window"]
    # The line takes the frame's value in place, its node kept (`patchLine`).
    # Degrees said short on the line (the ledger's ruling for the build's Task 2).
    assert page.text_content(f"{line} > .lv") == "3.50°"
    assert page.evaluate("(line) => document.querySelector(line).wlxSame === true", line)
    assert "changed" in page.get_attribute(line, "class").split()
    page.click('label[for="t-runtime"]')
    page.click('label[for="t-task"]')
    assert _opened(page) == ["fix_window"]
    _open(page, "fix_size")
    kept = page.evaluate("window.localStorage.getItem('wlx.opened.tasks/fixation_detection.py')")
    assert kept == "fix_size"

    page.reload()
    page.click('label[for="t-task"]')
    assert _opened(page) == ["fix_size"]
    assert page.is_visible(f'{_b("fix_size")} input[data-param="fix_size"]')

    _sectioned(rig, task="tasks/popout_search.py", trial_index=42)
    _until(page, "document.querySelector('#params .summary').getAttribute('data-task')"
                 " === 'tasks/popout_search.py'")
    assert _opened(page) == ["click a setting above to change it"]
    _sectioned(rig, trial_index=43)
    _until(page, "document.querySelector('#params .summary').getAttribute('data-task')"
                 " === 'tasks/fixation_detection.py'")
    assert _opened(page) == ["fix_size"]


def test_an_opened_setting_that_is_gone_shows_the_placeholder(rig):
    """The plan's Review Focus 2: the setting opened disappears -- a run without it, a group
    regrouped -- and the editor falls back to "click a setting above to change it", the stored
    name dropped, so it does not come back with the setting, and nothing is raised into the page.
    In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    errors = []
    page = _task6_page(rig, params=_group_rows(), groups=_move_up())
    page.on("pageerror", lambda error: errors.append(str(error)))
    key = "wlx.opened.tasks/fixation_detection.py"
    assert page.locator('#params > .summary .line[data-open="set_size"]').count() == 1
    _open(page, "set_size")
    assert _opened(page) == ["set_size"]

    _offer(rig, 41, params=tuple(row for row in _group_rows() if row.name != "set_size"),
           groups=_move_up())
    _until(page, "document.querySelector('#params .box[data-card=\"set_size\"]') === null")
    assert _opened(page) == ["click a setting above to change it"]
    assert page.evaluate(f"window.localStorage.getItem('{key}')") is None
    _offer(rig, 42, params=_group_rows(), groups=_move_up())
    _until(page, "document.querySelector('#params .box[data-card=\"set_size\"]') !== null")
    assert _opened(page) == ["click a setting above to change it"], "dropped, not kept"

    _open(page, "Move up")
    assert _opened(page) == ["Move up"]
    _offer(rig, 43, params=_group_rows(), groups=())
    _until(page, "document.querySelector('#params .box[data-card=\"move_up_bar\"]') !== null")
    assert _opened(page) == ["click a setting above to change it"]
    assert page.evaluate(f"window.localStorage.getItem('{key}')") is None
    assert page.locator('#params > .summary .line[aria-pressed="true"]').count() == 0
    assert errors == []


def test_a_group_line_opens_its_sentence(rig):
    """The summary and editor design's goal 6: a group is one line -- its title, its settings'
    values joined -- and one editor, its sentence with its fields in place and one Apply, which
    sends one `apply_many` of what it changed under one command id, as its box did on the grid.
    In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import ApplyMany, SetParameter

    page = _task6_page(rig, params=_group_rows(), groups=_move_up())
    line = '#params > .summary .line[data-open="Move up"]'
    assert page.locator(line).count() == 1, "a group is one line"
    assert page.text_content(f"{line} > .ln") == "Move up"
    assert page.text_content(f"{line} > .lv") == "80% · 50"
    assert page.locator('#params > .summary .line[data-open="move_up_bar"]').count() == 0

    _open(page, "Move up")
    assert _opened(page) == ["Move up"]
    box = _b("Move up")
    assert page.eval_on_selector_all(
        f"{box} .editor .sentence > *",
        "parts => parts.map((p) => p.matches('.gs') ? p.textContent : '[' +"
        " p.querySelector('input').value + ']')"
    ) == ["Move up when at least ", "[80]", " of the last ", "[50]", " answers are right"]
    page.fill(f'{box} input[data-param="move_up_bar"]', "90")
    page.fill(f'{box} input[data-param="move_up_window"]', "51")
    assert page.locator(f"{box} [data-apply]").count() == 1
    page.click(f"{box} [data-apply]")
    rig.wait_for(lambda: rig.dispatch.seen)
    time.sleep(0.3)  # housekeeping: room for a wrong second send to arrive

    (sent,) = rig.dispatch.seen
    assert type(sent) is ApplyMany and sent.cid
    assert [(type(change), change.name, change.value) for change in sent.changes] == [
        (SetParameter, "move_up_bar", 0.9), (SetParameter, "move_up_window", 51.0)]


def test_new_color_opens_from_the_colors_section(rig):
    """The summary and editor design's call "Colors: the *New color…* panel opens from the Colors
    section's header in the summary, into the editor": the Colors section's lines end with *New
    color…*, which opens its section's panel in the editor, unfolded, the color boxes hidden; what
    is typed in it stays across a frame; opening a color box hides it again. In a real browser:
    run with `WLX_BROWSER=webkit` too, for Safari."""
    from pathlib import Path

    from wl_xcon.link import ParamRow, decode, encode
    from wl_xcon.photometry import ColorSet

    isohue = ColorSet.load(Path(__file__).parent / "fixtures" / "isohue_design.json")
    color = {
        "sets": {"isohue": {"apex": list(isohue.apex), "luminance_cd_m2": 15.0,
                            "design": dict(isohue.design),
                            "hues": {hue: {"xy": list(xy), "srgb": "#808080"}
                                     for hue, xy in isohue.colors.items()}}},
        "set": "isohue", "hue": "green", "approximate": True,
        "saturation": {"setting": None, "value": 1.0, "cd_m2": 15.0},
        "luminance": {"setting": None, "value": 15.0, "cd_m2": 15.0, "set_wide": False},
    }
    rows = (ParamRow.of("fix_hold", "s", 0.1, 1.0, 0.3, False, section="Timing"),
            ParamRow.of("odd_color", "appearance", None, None, None, False, source="run",
                        color=color, section="Colors"),
            ParamRow.of("distractor_color", "appearance", None, None, None, False, source="run",
                        color=color, section="Colors"))
    rig.hub.offer(decode(encode(frame(params=rows))))
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    colors = page.eval_on_selector_all(
        '#params > .summary .ssec[data-section="Colors"] > .line',
        "lines => lines.map((line) => line.getAttribute('data-open'))")
    assert colors == ["odd_color", "distractor_color", "new-color:Colors"], colors

    _open(page, "new-color:Colors")
    assert _opened(page) == ["Colors"]
    assert page.evaluate("document.querySelector('#params > .editing > [data-newc=\"Colors\"]').open")
    page.fill('[data-newc="Colors"] input[data-newc-name]', "violet")
    rig.hub.offer(decode(encode(frame(params=rows, trial_index=41))))
    _arrived(page, 41)
    assert _opened(page) == ["Colors"]
    assert page.input_value('[data-newc="Colors"] input[data-newc-name]') == "violet"
    _open(page, "odd_color")
    assert _opened(page) == ["odd_color"]
    assert not page.is_visible('[data-newc="Colors"]')


def test_runtime_still_needed_reads_as_words_at_three_widths(rig):
    """The workflow review's F12: Runtime's "Still needed" drew `this block has no percentage
    rule, so this changes nothing here` one letter per line down 950 px. At 1024, 1280 and 1440
    wide, each sentence of the pane's rows is at least eight ems wide and no taller than three of
    its lines. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(frame(rule=None, clearing=False, owed={"ecc 10": 18}))))
    page = rig.browser_page()
    page.wait_for_selector("#rt-need .kv .nm", state="visible")
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": LAPTOP_H})
        shapes = page.evaluate("""() => Array.from(document.querySelectorAll('#rt-need .kv > .nm'))
          .map((span) => {
            const rect = span.getBoundingClientRect();
            const line = parseFloat(getComputedStyle(span).lineHeight) ||
              1.4 * parseFloat(getComputedStyle(span).fontSize);
            const em = parseFloat(getComputedStyle(span).fontSize);
            return [span.textContent.slice(0, 40), rect.width / em, rect.height / line];
          })""")
        assert any("no percentage rule" in said for said, _, _ in shapes), shapes
        narrow = [(said, round(wide, 1), round(tall, 1)) for said, wide, tall in shapes
                  if wide < 8 or tall > 3.2]
        assert narrow == [], (width, narrow)


# --- the console interface rework's Task 6: drafts, Apply, Apply all and withdraw ---------------
#
# The PI, 2026-11-19: "i prefer an apply button in each box for making a change". Nothing a box
# holds is sent until its Apply, Enter in one of its fields, or Apply all; each box says where it
# stands in one status line (the plan's "Words on the page"); a frame is patched box by box, so a
# press lands on a node no frame replaced. Through the wire, in a real browser: each runs in
# Chromium in the suite and in WebKit (`WLX_BROWSER=webkit`), for Safari, by the builder.

def _b(name: str, root: str = "#params") -> str:
    return f'{root} .box[data-card="{name}"]'


def _say(page, name: str, root: str = "#params") -> str:
    return page.text_content(f"{_b(name, root)} > .status > .say").strip()


def _says(rig, page, name: str, said: str, root: str = "#params", start: bool = False) -> None:
    """Wait until box `name`'s status line says `said` (or starts with it), failing with what it
    said instead."""
    end = time.monotonic() + WAIT_S
    while time.monotonic() < end:
        now = _say(page, name, root)
        if (now.startswith(said) if start else now == said):
            return
        page.wait_for_timeout(50)
    pytest.fail(f"{name}'s status line says {_say(page, name, root)!r}, not {said!r}")


def _classes(page, name: str, root: str = "#params") -> list:
    return page.get_attribute(_b(name, root), "class").split()


def _head(page, name: str, root: str = "#params") -> str:
    return page.text_content(f"{_b(name, root)} > .head .now").strip()


def _bar(page) -> str | None:
    """The drafts bar's words, or None while it is hidden."""
    if not page.is_visible("#drafts"):
        return None
    return page.text_content("#drafts-say").strip()


def _sent_of(rig, kind) -> list:
    return [seen for seen in rig.dispatch.seen if isinstance(seen, kind)]


def _task6_rows(hold=0.3, deadline=0.6, size=4, **over):
    """A Timing section's two holds, a whole count in Stimuli and the reward size, each as the rig
    makes their rows (`ParamRow.of`): `fix_hold` 0.1 to 1 s at a 0.05 step, `set_size` 1 to 36
    whole; `over` replaces fields of a row by its name."""
    from wl_xcon.link import ParamRow

    rows = {
        "fix_hold": ParamRow.of("fix_hold", "s", 0.1, 1.0, hold, False, source="task", step=0.05,
                                section="Timing"),
        "response_deadline": ParamRow.of("response_deadline", "s", 0.2, 2.0, deadline, False,
                                         source="task", step=0.05, section="Timing"),
        "set_size": ParamRow.of("set_size", "objects", 1.0, 36.0, size, False, source="task",
                                whole=True, step=1.0, section="Stimuli"),
        "reward_correct": ParamRow.of("reward_correct", "mL", 0.0, 0.4, 0.15, True, step=0.01),
    }
    for name, fields in over.items():
        rows[name] = dataclasses.replace(rows[name], **fields)
    return tuple(rows.values())


def _task6_page(rig, trial=40, **fields):
    _offer(rig, trial, params=fields.pop("params", _task6_rows()), **fields)
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    page.wait_for_selector(_b("fix_hold"), state="visible")
    return page


def test_nothing_is_sent_until_apply(rig):
    """The design's goal 2: typing, −/+ (Shift-click steps ten times as far) and a segment of the
    fixed/drawn switch each make a draft the box shows as *not sent*, and nothing is sent -- past
    the 600 ms the old fields and arrows waited before sending on their own; the head still says
    the value in force; a frame arriving leaves every draft; the drafts bar counts them in the
    boxes' order."""
    from wl_xcon.link import ParamRow

    wait = ParamRow.of("wait", "s", 0.05, 2.0, 0.5, False, source="task", step=0.05,
                       switch="drawn", section="Timing")
    page = _task6_page(rig, params=_task6_rows() + (wait,))

    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    page.click(f'{_b("set_size")} [data-dir="1"]')
    page.click(f'{_b("set_size")} [data-dir="1"]', modifiers=["Shift"])
    page.click(f'{_b("wait")} [data-switch="drawn"]')
    page.fill(f'{_b("wait")} [data-fields="non_aging"] input[data-form="shortest"]', "0.4")
    page.fill(f'{_b("wait")} [data-fields="non_aging"] input[data-form="longest"]', "0.9")
    _offer(rig, 41, params=_task6_rows() + (wait,))
    _arrived(page, 41)
    time.sleep(0.8)  # housekeeping: past the old fields' and arrows' 600 ms

    assert rig.dispatch.seen == []
    for name in ("fix_hold", "set_size", "wait"):
        assert _say(page, name) == "not sent", name
        assert "draft" in _classes(page, name), name
    assert page.input_value(f'{_b("set_size")} input[data-param="set_size"]') == "15"
    assert page.input_value(f'{_b("fix_hold")} input[data-param="fix_hold"]') == "0.5"
    assert _head(page, "fix_hold") == "0.30 s"
    assert _head(page, "set_size") == "4 objects"
    assert page.is_visible(f'{_b("wait")} [data-side="drawn"]')
    assert _bar(page) == "3 edits not sent: fix_hold, wait, set_size"
    assert "draft" not in _classes(page, "response_deadline")


def test_escape_leaves_a_drawn_settings_shape_select_and_returns_to_its_line(rig, tmp_path):
    """The pop-out revision's whole-build review, M3 (the summary and editor design's goal 7): in
    a drawn setting's editor **Esc leaves the shape `<select>`**, and a second Esc returns to the
    setting's summary line, as from a field. In a real browser: run with `WLX_BROWSER=webkit` too,
    for Safari."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_frame(tmp_path))))
    page = rig.browser_page()
    _sign_in(page)
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    page.click('label[for="t-task"]')
    _open(page, "fix_hold")
    shape = f'{_b("fix_hold")} select'
    page.focus(shape)
    assert page.evaluate("document.activeElement.tagName") == "SELECT"
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.tagName") != "SELECT"
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.getAttribute('data-open')") == "fix_hold"


def test_enter_applies_and_escape_undoes(rig):
    """The controls review's F7, as the design takes it: in a box's field Esc puts the box back to
    the value in force, the field keeping focus, and a second Esc leaves the field; ↑ and ↓ step
    it, Shift ten steps; Enter is Apply, sending the box's one change under a command id of the
    page's own, and the box says *sending…* until a frame answers it."""
    from wl_xcon.link import SetParameter

    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'

    page.fill(field, "0.5")
    assert _say(page, "fix_hold") == "not sent"
    page.press(field, "Escape")
    assert page.input_value(field) == "0.30"
    assert _say(page, "fix_hold") == "0.10 to 1.00"
    assert page.evaluate("document.activeElement.getAttribute('data-param')") == "fix_hold"
    page.press(field, "Escape")
    assert page.evaluate("document.activeElement.getAttribute('data-param')") is None

    size = f'{_b("set_size")} input[data-param="set_size"]'
    page.focus(size)
    page.press(size, "ArrowUp")
    assert page.input_value(size) == "5"
    page.press(size, "Shift+ArrowUp")
    assert page.input_value(size) == "15"
    page.press(size, "Escape")
    assert page.input_value(size) == "4"

    page.fill(field, "0.45")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    _says(rig, page, "fix_hold", "sending…")

    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.value, sent.by.name) == (
        SetParameter, "fix_hold", 0.45, "Jake Westerberg")
    assert isinstance(sent.cid, str) and 1 <= len(sent.cid) <= 64
    assert page.is_disabled(f'{_b("fix_hold")} [data-apply]')


def test_a_draft_equal_to_the_value_in_force_is_no_draft(rig):
    """The controls review's §2, rule 4: typing a value back to the one in force, as a number
    (`0.3` is `0.30`), or stepping away and back, clears *not sent*: no draft, no Apply, nothing
    in the drafts bar."""
    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'

    page.fill(field, "0.8")
    assert _say(page, "fix_hold") == "not sent" and _bar(page) == "1 edit not sent: fix_hold"
    page.fill(field, "0.3")
    assert _say(page, "fix_hold") == "0.10 to 1.00"
    assert "draft" not in _classes(page, "fix_hold")
    assert not page.is_visible(f'{_b("fix_hold")} [data-apply]')
    assert _bar(page) is None
    page.click(f'{_b("set_size")} [data-dir="1"]')
    assert _say(page, "set_size") == "not sent"
    page.click(f'{_b("set_size")} [data-dir="-1"]')
    assert _say(page, "set_size") == "1 to 36 · whole number"
    assert _bar(page) is None
    assert rig.dispatch.seen == []


def test_the_box_walks_through_its_states(rig):
    """The design's goal 4, every outcome in one reserved line: *not sent* → *sending…* →
    *waiting · you* (the rig's staged row naming the page's command id, the head
    saying what waits, *withdraw* offered) → *in force from trial N*; then *refused <value> ·
    <reason>*, the draft kept for correction with Apply live; and *in force, with a warning*."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, Refused, Staged

    jake = Box("Jake Westerberg")
    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'

    page.fill(field, "0.5")
    assert _say(page, "fix_hold") == "not sent"
    page.click(f'{_b("fix_hold")} [data-apply]')
    rig.wait_for(lambda: rig.dispatch.seen)
    assert _say(page, "fix_hold") == "sending…"
    cid = rig.dispatch.seen[-1].cid
    _offer(rig, 41, params=_task6_rows(), staged=(Staged("fix_hold", 0.3, 0.5, jake, False, cid=cid),))
    _says(rig, page, "fix_hold", "waiting · you")
    assert _head(page, "fix_hold") == "0.30 → 0.50 s"
    assert page.is_visible(f'{_b("fix_hold")} [data-withdraw="{cid}"]')
    assert "staged" in _classes(page, "fix_hold") and "draft" not in _classes(page, "fix_hold")
    _offer(rig, 42, params=_task6_rows(0.5, fix_hold={"applied": Applied(42, str(jake))}))
    _says(rig, page, "fix_hold", "in force from trial 42")
    assert page.input_value(field) == "0.50"

    page.fill(field, "0.95")
    page.press(field, "Enter")
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    again = rig.dispatch.seen[-1].cid
    why = ("'fix_hold' at 0.95 is refused, and the previous value stands: the hold and the time "
           "to acquire the point no longer fit inside the timeout")
    _offer(rig, 43, params=_task6_rows(0.5, fix_hold={"applied": Applied(42, str(jake))}),
           refusals=(Refused("fix_hold", jake, why, cid=again, value=0.95),))
    _says(rig, page, "fix_hold", "refused 0.95 · the hold and the time to acquire", start=True)
    assert page.input_value(field) == "0.95"
    assert {"refused", "draft"} <= set(_classes(page, "fix_hold"))
    assert page.is_visible(f'{_b("fix_hold")} [data-apply]')
    assert not page.is_disabled(f'{_b("fix_hold")} [data-apply]')

    page.fill(f'{_b("response_deadline")} input[data-param="response_deadline"]', "0.8")
    page.click(f'{_b("response_deadline")} [data-apply]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 3)
    warned = "crowded-array: 12 objects on a 6° ring leave 1.1° between windows of 1.6°"
    _offer(rig, 44, params=_task6_rows(0.5, 0.8, fix_hold={"applied": Applied(42, str(jake))},
                                       response_deadline={"applied": Applied(44, str(jake)),
                                                          "warned": (warned,)}),
           refusals=(Refused("fix_hold", jake, why, cid=again, value=0.95),))
    _says(rig, page, "response_deadline", "in force, with a warning · from trial 44")
    assert "warned" in _classes(page, "response_deadline")


def test_a_later_accepted_change_clears_the_refusal(rig):
    """The design's goal 4: "a refusal is cleared by a later accepted change of that setting". The
    frame keeps its last refusals, so the rig still sends this one after a later change of the
    setting was staged and applied; the box says the change in force, not the old refusal, and so
    does its summary line, the rig's ! dropped (the summary and editor build's Task 2: the page's
    "cleared-refusal marks")."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, Refused, Staged

    jake = Box("Jake Westerberg")
    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.95")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    refused = (Refused("fix_hold", jake, "'fix_hold' at 0.95 is refused, and the previous value "
                       "stands: it does not fit", cid=rig.dispatch.seen[-1].cid, value=0.95),)
    _offer(rig, 41, params=_task6_rows(), refusals=refused)
    _says(rig, page, "fix_hold", "refused 0.95 · it does not fit")

    page.fill(field, "0.4")
    page.press(field, "Enter")
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    cid = rig.dispatch.seen[-1].cid
    _offer(rig, 42, params=_task6_rows(), refusals=refused,
           staged=(Staged("fix_hold", 0.3, 0.4, jake, False, cid=cid),))
    _says(rig, page, "fix_hold", "waiting · you")
    _offer(rig, 43, params=_task6_rows(0.4, fix_hold={"applied": Applied(43, str(jake))}),
           refusals=refused)

    _says(rig, page, "fix_hold", "in force from trial 43")
    assert "refused" not in _classes(page, "fix_hold")
    assert "applied" in _classes(page, "fix_hold")
    assert page.get_attribute(_line("fix_hold"), "data-said").startswith("refused 0.95"), (
        "the rig's line still says the refusal")
    assert _marked(page, "fix_hold") == ("", "0.40 s", "fix_hold · 0.40 s · in force from trial 43")
    assert "refused" not in page.get_attribute(_line("fix_hold"), "class").split()


def test_apply_all_sends_one_command_and_both_take_effect_on_one_trial(rig):
    """The design's goal 2: "Apply all stages them together, on the same trial". Two drafts, one
    press: one `apply_many` of both changes under one command id; both boxes say *sending…*, then
    *waiting* as the rig stages them under that id, and *in force from trial 41* together."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, ApplyMany, SetParameter, Staged

    jake = Box("Jake Westerberg")
    page = _task6_page(rig)
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    page.fill(f'{_b("response_deadline")} input[data-param="response_deadline"]', "0.8")
    assert _bar(page) == "2 edits not sent: fix_hold, response_deadline"

    page.click("#drafts-apply")
    rig.wait_for(lambda: rig.dispatch.seen)
    time.sleep(0.3)  # housekeeping: room for a wrong second send to arrive

    (sent,) = rig.dispatch.seen
    assert type(sent) is ApplyMany and sent.by.name == "Jake Westerberg"
    assert [(type(change), change.name, change.value) for change in sent.changes] == [
        (SetParameter, "fix_hold", 0.5), (SetParameter, "response_deadline", 0.8)]
    assert _say(page, "fix_hold") == _say(page, "response_deadline") == "sending…"
    assert _bar(page) is None
    _offer(rig, 41, params=_task6_rows(), staged=(
        Staged("fix_hold", 0.3, 0.5, jake, False, cid=sent.cid),
        Staged("response_deadline", 0.6, 0.8, jake, False, cid=sent.cid)))
    _says(rig, page, "response_deadline", "waiting · you")
    assert _say(page, "fix_hold") == "waiting · you"
    applied = Applied(41, str(jake))
    _offer(rig, 42, params=_task6_rows(0.5, 0.8, fix_hold={"applied": applied},
                                       response_deadline={"applied": applied}))
    _says(rig, page, "response_deadline", "in force from trial 41")
    assert _say(page, "fix_hold") == "in force from trial 41"


def test_a_reward_box_is_left_out_of_apply_all_and_says_so(rig):
    """The design's call (XC-527): a reward size is sent alone, by its own Apply, never in Apply
    all and never withdrawn, and its box says so ("sent alone · cannot be withdrawn"); the bar says
    so too, and Apply all sends the rest without it."""
    from wl_xcon.actor import Box
    from wl_xcon.link import ApplyMany, SetParameter, Staged

    page = _task6_page(rig)
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    page.fill(f'{_b("reward_correct")} input[data-param="reward_correct"]', "0.2")

    assert _say(page, "reward_correct") == "not sent · sent alone · cannot be withdrawn"
    assert _bar(page) == ("2 edits not sent: fix_hold, reward_correct · reward_correct is sent "
                          "alone, by its own Apply")
    page.click("#drafts-apply")
    rig.wait_for(lambda: rig.dispatch.seen)
    (together,) = rig.dispatch.seen
    assert type(together) is ApplyMany and [c.name for c in together.changes] == ["fix_hold"]
    assert _bar(page) == "1 edit not sent: reward_correct · reward_correct is sent alone, by its own Apply"
    assert page.is_disabled("#drafts-apply")
    assert _say(page, "reward_correct") == "not sent · sent alone · cannot be withdrawn"

    page.click(f'{_b("reward_correct")} [data-apply]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    alone = rig.dispatch.seen[-1]
    assert (type(alone), alone.name, alone.value) == (SetParameter, "reward_correct", 0.2)
    _offer(rig, 41, params=_task6_rows(), staged=(
        Staged("reward_correct", 0.15, 0.2, Box("Jake Westerberg"), True, cid=alone.cid),))
    _says(rig, page, "reward_correct", "waiting · you")
    assert page.locator(f'{_b("reward_correct")} [data-withdraw]').count() == 0


def test_withdraw_on_one_box_says_it_takes_back_the_whole_act(rig):
    """The design's call: "withdrawing from any of its boxes withdraws all of it, and the box says
    so first". Three applied together each offer *withdraw all 3*, its title naming them; one
    press sends one `withdraw` of the act's id, and all three go back to the value in force,
    saying so. And the plan's Review Focus 3: a withdrawal after the boundary passed is refused,
    "already in force from trial N", and the box says it is in force."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, Refused, Staged, Withdraw

    jake = Box("Jake Westerberg")
    page = _task6_page(rig)
    for name, value in (("fix_hold", "0.5"), ("response_deadline", "0.8"), ("set_size", "6")):
        page.fill(f'{_b(name)} input[data-param="{name}"]', value)
    page.click("#drafts-apply")
    rig.wait_for(lambda: rig.dispatch.seen)
    cid = rig.dispatch.seen[-1].cid
    staged = (Staged("fix_hold", 0.3, 0.5, jake, False, cid=cid),
              Staged("response_deadline", 0.6, 0.8, jake, False, cid=cid),
              Staged("set_size", 4, 6, jake, False, cid=cid))
    _offer(rig, 41, params=_task6_rows(), staged=staged)
    _says(rig, page, "set_size", "waiting · you")

    for name in ("fix_hold", "response_deadline", "set_size"):
        button = f'{_b(name)} [data-withdraw="{cid}"]'
        assert page.text_content(button) == "withdraw all 3", name
        assert page.get_attribute(f'{_b(name)} .wd', "title") == (
            "withdraws the 3 applied together: fix_hold, response_deadline, set_size")
    page.click(f'{_b("set_size")} [data-withdraw="{cid}"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    assert _say(page, "fix_hold") == "withdrawing…"
    _offer(rig, 42, params=_task6_rows(), withdrawals=(cid,))
    for name, value in (("fix_hold", "0.30"), ("response_deadline", "0.60"), ("set_size", "4")):
        _says(rig, page, name, "withdrawn · it never applied")
        assert page.input_value(f'{_b(name)} input[data-param="{name}"]') == value, name
    taken = rig.dispatch.seen[-1]
    assert (type(taken), taken.cid) == (Withdraw, cid)
    assert len(_sent_of(rig, Withdraw)) == 1

    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.5")
    page.press(field, "Enter")
    rig.wait_for(lambda: len(rig.dispatch.seen) == 3)
    late = rig.dispatch.seen[-1].cid
    _offer(rig, 43, params=_task6_rows(), staged=(Staged("fix_hold", 0.3, 0.5, jake, False, cid=late),))
    _says(rig, page, "fix_hold", "waiting · you")
    assert page.text_content(f'{_b("fix_hold")} [data-withdraw]') == "withdraw"
    page.click(f'{_b("fix_hold")} [data-withdraw="{late}"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 4)
    why = (f"the change sent as '{late}' is not withdrawn: it is already in force from trial 44, "
           "so nothing of it waits to be taken back; change the setting again to move it")
    _offer(rig, 44, params=_task6_rows(0.5, fix_hold={"applied": Applied(44, str(jake))}),
           refusals=(Refused("withdraw", jake, why, cid=late),))
    _says(rig, page, "fix_hold", "not withdrawn · it is already in force from trial 44", start=True)
    assert "applied" in _classes(page, "fix_hold")
    assert page.input_value(field) == "0.50"


def test_a_withdrawal_answered_after_the_next_frame_still_puts_the_box_back(rig):
    """A withdrawal's answer may come after the frame that shows the act no longer waiting (found
    under the suite's load in the console interface rework's Task 7, on
    `test_withdraw_on_one_box_says_it_takes_back_the_whole_act`): that frame has not applied the
    act, so the box keeps no draft of what it sent, and once the answer comes it goes back to the
    value in force, saying it was withdrawn. The rig here answers the withdrawal a second late."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Staged, Withdraw

    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.5")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    cid = rig.dispatch.seen[-1].cid
    _offer(rig, 41, params=_task6_rows(),
           staged=(Staged("fix_hold", 0.3, 0.5, Box("Jake Westerberg"), False, cid=cid),))
    _says(rig, page, "fix_hold", "waiting · you")
    page.evaluate("document.activeElement.blur()")

    rig.dispatch.delay = 1.0
    page.click(f'{_b("fix_hold")} [data-withdraw="{cid}"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    _offer(rig, 42, params=_task6_rows(), withdrawals=(cid,))
    _arrived(page, 42)
    assert _say(page, "fix_hold") != "not sent" and _bar(page) is None

    _says(rig, page, "fix_hold", "withdrawn · it never applied")
    assert page.input_value(field) == "0.30" and _bar(page) is None
    assert [type(seen) for seen in rig.dispatch.seen][-1] is Withdraw


def test_a_withdrawal_is_said_done_only_on_the_rigs_word(rig):
    """The whole-build review's I1, its probe: a withdrawal answered *sent* whose act waits no more
    has not been shown withdrawn -- a frame in which the change is in force instead (the boundary
    applied it before the press arrived) leaves the box saying *withdrawing…*, never "withdrawn ·
    it never applied"; the rig's refusal that follows is said. And a withdrawal the rig did is
    said withdrawn only on the frame that lists its act (`Telemetry.withdrawals`)."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, Refused, Staged

    jake = Box("Jake Westerberg")
    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.5")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    cid = rig.dispatch.seen[-1].cid
    _offer(rig, 41, params=_task6_rows(), staged=(Staged("fix_hold", 0.3, 0.5, jake, False, cid=cid),))
    _says(rig, page, "fix_hold", "waiting · you")
    page.evaluate("document.activeElement.blur()")
    page.click(f'{_b("fix_hold")} [data-withdraw="{cid}"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    rig.wait_for(lambda: page.text_content("#sent").strip().startswith("sent"))

    in_force = _task6_rows(0.5, fix_hold={"applied": Applied(42, str(jake))})
    _offer(rig, 42, params=in_force)
    _arrived(page, 42)
    assert _say(page, "fix_hold") == "withdrawing…"
    assert float(page.input_value(field)) == 0.5
    why = (f"the change sent as '{cid}' is not withdrawn: it is already in force from trial 42, "
           "so nothing of it waits to be taken back; change the setting again to move it")
    _offer(rig, 43, params=in_force, refusals=(Refused("withdraw", jake, why, cid=cid),))
    _says(rig, page, "fix_hold", "not withdrawn · it is already in force from trial 42", start=True)

    page.fill(field, "0.6")
    page.press(field, "Enter")
    rig.wait_for(lambda: len(rig.dispatch.seen) == 3)
    again = rig.dispatch.seen[-1].cid
    _offer(rig, 44, params=in_force, refusals=(Refused("withdraw", jake, why, cid=cid),),
           staged=(Staged("fix_hold", 0.5, 0.6, jake, False, cid=again),))
    _says(rig, page, "fix_hold", "waiting · you")
    page.evaluate("document.activeElement.blur()")
    page.click(f'{_b("fix_hold")} [data-withdraw="{again}"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 4)
    _offer(rig, 45, params=in_force, refusals=(Refused("withdraw", jake, why, cid=cid),))
    _arrived(page, 45)
    assert _say(page, "fix_hold") == "withdrawing…"
    _offer(rig, 46, params=in_force, refusals=(Refused("withdraw", jake, why, cid=cid),),
           withdrawals=(again,))
    _says(rig, page, "fix_hold", "withdrawn · it never applied")
    assert page.input_value(field) == "0.50"


def test_an_act_the_rig_never_answers_lets_its_box_go(rig):
    """The whole-build review's I2, its probe: an Apply answered *sent* that no frame then answers
    -- here another person's 0.35 comes into force and nothing names the act -- never leaves its
    box *sending…* with Apply, Discard and Esc dead. Esc lets it go at once, the box back to the
    value in force, saying the rig has not confirmed it, once a frame has come without the rig's
    word (before one, see the next test); and left alone, `ANSWER_FRAMES` frames
    later the box says so itself, the edit a draft again, Apply and Discard live, until its news
    changes."""
    from wl_xcon.link import Applied

    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    other = _task6_rows(0.35, fix_hold={"applied": Applied(41, "Kim")})
    unconfirmed = "not confirmed by the rig · check the value in force"

    page.fill(field, "0.5")
    page.evaluate("document.getElementById('sent').textContent = ''")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    rig.wait_for(lambda: page.text_content("#sent").strip().startswith("sent"))
    assert page.is_disabled(f'{_b("fix_hold")} [data-discard]'), "held until a frame has come"
    _offer(rig, 41, params=other)
    _arrived(page, 41)
    assert _say(page, "fix_hold") == "sending…"
    assert not page.is_disabled(f'{_b("fix_hold")} [data-discard]'), "Discard lets it go"
    page.focus(field)
    page.press(field, "Escape")
    _says(rig, page, "fix_hold", unconfirmed)
    assert page.input_value(field) == "0.35" and _bar(page) is None

    page.fill(field, "0.5")
    page.evaluate("document.getElementById('sent').textContent = ''")
    page.press(field, "Enter")
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    rig.wait_for(lambda: page.text_content("#sent").strip().startswith("sent"))
    page.evaluate("document.activeElement.blur()")
    for trial in (42, 43):
        _offer(rig, trial, params=other)
        _arrived(page, trial)
        assert _say(page, "fix_hold") == "sending…", trial
    _offer(rig, 44, params=other)
    _says(rig, page, "fix_hold", unconfirmed)
    assert page.input_value(field) == "0.5" and "draft" in _classes(page, "fix_hold")
    assert not page.is_disabled(f'{_b("fix_hold")} [data-apply]')
    assert not page.is_disabled(f'{_b("fix_hold")} [data-discard]')
    _offer(rig, 45, params=_task6_rows(0.4, fix_hold={"applied": Applied(45, "Kim")}))
    _says(rig, page, "fix_hold", "not sent · Kim changed this from trial 45")


def test_enter_then_escape_before_a_frame_keeps_the_change_on_its_way(rig):
    """The fix wave's re-review, N1: type, Enter, Esc to leave the field -- the design's keys, done
    before the rig's next frame -- never discards a change the rig has: the line stays *sending…*,
    the field keeps the sent value, Discard stays held, Esc leaves the field, and the frame that
    then shows it waiting says *waiting · you*. Discard and Esc let an answered act go only once a
    frame has passed without the rig's word on it. Run in WebKit too, for Safari."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Staged

    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.5")
    page.evaluate("document.getElementById('sent').textContent = ''")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    rig.wait_for(lambda: page.text_content("#sent").strip().startswith("sent"))
    assert page.is_disabled(f'{_b("fix_hold")} [data-discard]'), "Discard held before any frame"
    page.press(field, "Escape")
    assert page.evaluate("document.activeElement.getAttribute('data-param')") is None, (
        "Esc with no draft leaves the field")
    assert _say(page, "fix_hold") == "sending…"
    assert page.input_value(field) == "0.5" and _bar(page) is None
    cid = rig.dispatch.seen[-1].cid
    _offer(rig, 41, params=_task6_rows(),
           staged=(Staged("fix_hold", 0.3, 0.5, Box("Jake Westerberg"), False, cid=cid),))
    _says(rig, page, "fix_hold", "waiting · you")
    assert page.input_value(field) == "0.5"


def test_a_fault_in_the_answers_handler_is_never_said_not_delivered(rig):
    """The whole-build review's M4: `deliver`'s "not delivered" is for a command that did not reach
    `wlx serve`, never for one whose answer came and whose handler then raised -- here a page fault
    made while the rig took a second to answer. The answer's own words stay."""
    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.5")
    rig.dispatch.delay = 1.0
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    # The fault: `CSS.escape`, which the page's answer handler calls (`cardOf`), raises until the
    # page puts it back itself, 2.5 s on -- Playwright's own calls use it too, so none is made
    # meanwhile; what `#sent` says is gathered by the page as it changes.
    page.evaluate("""() => {
        const sent = document.getElementById('sent');
        window.__said = [];
        new MutationObserver(() => window.__said.push(sent.textContent.trim())).observe(
            sent, {childList: true, characterData: true, subtree: true});
        const escape = CSS.escape;
        CSS.escape = () => { throw new Error('a fault in the answer handler'); };
        setTimeout(() => { CSS.escape = escape; }, 2500);
    }""")
    time.sleep(3.0)  # housekeeping: the answer comes at 1 s, the page's fault ends at 2.5 s
    said = page.evaluate("window.__said")
    assert said and said[-1] == "sent: test", said
    assert not any(line.startswith("not delivered") for line in said), said


def test_a_change_under_a_draft_leaves_the_draft_and_says_who(rig):
    """The plan's Review Focus 4: someone else changes a setting under a trainer's draft (another
    console, a staircase, a revert): the draft is untouched, the head shows the new value in force,
    and the status says who changed it -- while it waits, and once it is in force; the trainer's
    Apply still sends the draft."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, SetParameter, Staged

    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.8")
    _offer(rig, 41, params=_task6_rows(), staged=(
        Staged("fix_hold", 0.3, 0.6, Box("Ana"), False, cid="other-console-1"),))
    _arrived(page, 41)

    _says(rig, page, "fix_hold", "not sent · Ana (box, unverified) is changing this to 0.60")
    assert page.input_value(field) == "0.8"
    assert _head(page, "fix_hold") == "0.30 → 0.60 s"
    page.evaluate("document.activeElement.blur()")
    _offer(rig, 42, params=_task6_rows(0.6, fix_hold={"applied": Applied(42, "Ana (box, unverified)")}))
    _arrived(page, 42)
    _says(rig, page, "fix_hold", "not sent · Ana (box, unverified) changed this from trial 42")
    assert page.input_value(field) == "0.8"
    assert _head(page, "fix_hold") == "0.60 s"

    page.click(f'{_b("fix_hold")} [data-apply]')
    rig.wait_for(lambda: rig.dispatch.seen)
    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.value) == (SetParameter, "fix_hold", 0.8)


def _matrix_rows(trial):
    """The boxes a press is tried on, each with a head the frame of trial 41 changes: a plain
    field, a whole count's −/+, a timing switch, a pool's ticks (66, then 70: blue among green
    added), a color's swatches and a held setting's *hand back*."""
    from wl_xcon.link import ParamRow

    later = trial > 40
    color = {
        "sets": {"isohue": {"apex": [0.31272, 0.329], "luminance_cd_m2": 15.0, "design": None,
                            "hues": {"green": {"xy": [0.31324, 0.50711], "srgb": "#4a9a3e"},
                                     "red": {"xy": [0.45955, 0.32918], "srgb": "#c76f6a"}}}},
        "set": "isohue", "hue": "green", "approximate": True,
        "saturation": {"setting": None, "value": 1.0, "cd_m2": 15.0},
        "luminance": {"setting": None, "value": 15.0, "cd_m2": 15.0, "set_wide": False},
    }
    look = ParamRow.of("distractor_appearance", "appearance", None, None, None, False,
                       source="run", color=color, section="Colors")
    look = dataclasses.replace(look, words="Disc, " + ("darker" if later else "green"))
    return _task6_rows(0.35 if later else 0.3, size=6 if later else 4) + (
        ParamRow.of("wait", "s", 0.05, 2.0, 0.55 if later else 0.5, False, source="task",
                    step=0.05, switch="drawn", section="Timing"),
        ParamRow.of("gap", "s", 0.1, 2.0, 0.65 if later else 0.6, False, source="person",
                    conditions=("near",), step=0.05, section="Timing"),
        look, _pool_row(70 if later else 66))


_PRESSED = {
    "field": (_b("fix_hold") + ' input[data-param="fix_hold"]', "fix_hold", "0.35 s"),
    "stepper": (_b("set_size") + ' [data-dir="1"]', "set_size", "6 objects"),
    "segment": (_b("wait") + ' [data-switch="drawn"]', "wait", "0.55 s"),
    "tick": (_b("pairings") + ' input.tick[aria-label="green among red"]', "pairings",
             "3 of 12 pairs"),
    "swatch": (_b("distractor_appearance") + ' .hue[data-color="red"]', "distractor_appearance",
               "Disc, darker"),
    "apply": (_b("fix_hold") + " [data-apply]", "fix_hold", "0.35 s"),
    "withdraw": (_b("fix_hold") + " [data-withdraw]", "fix_hold", "0.35 → 0.50 s"),
    "hand back": (_b("gap") + ' [data-cmd="hand_back"]', "gap", "0.65 s"),
    # A summary line (the summary and editor build's Task 2: the plan's Review Focus 1).
    "line": ('#params > .summary .line[data-open="set_size"]', "set_size", "6 objects"),
    # Runtime's pinned line and its box's + there (the summary and editor build's Task 3).
    "pinned line": ('#pinned > .line[data-open="set_size"]', "set_size", "6 objects"),
    "pinned stepper": ('#pinned-editing > .box[data-pin="set_size"] [data-dir="1"]', "set_size",
                       "6 objects"),
}


@pytest.mark.parametrize("control", [
    "field", "stepper", "segment", "tick", "swatch", "apply", "withdraw", "hand back", "line",
    "pinned line", "pinned stepper"])
def test_a_press_during_frames_acts_once(rig, control):
    """The plan's Review Focus 1: a frame lands while a trainer presses a box's control -- a field,
    −/+, a segment of the switch, a tick, a swatch, Apply, *withdraw*, *hand back*, a summary line
    (the summary and editor build's Task 2, which opens its setting), Runtime's pinned line and
    its box's + there (the build's Task 3) -- a frame that
    changes that box's head and every neighbor's: the press acts once, and the box shows the
    frame's news after. The mouse goes down, the frame of trial 41 arrives, the mouse comes up.
    Run in WebKit too, where earlier fix rounds found a frame replacing the button under a press."""
    from wl_xcon.actor import Box
    from wl_xcon.link import HandBack, SetColor, SetParameter, Staged, Withdraw

    jake = Box("Jake Westerberg")
    page = _task6_page(rig, params=_matrix_rows(40))
    if control == "hand back":
        _more(page)
    if control.startswith("pinned"):
        _pin(page, "set_size")
        page.click('label[for="t-runtime"]')
        if control == "pinned stepper":
            page._page.click('#pinned > .line[data-open="set_size"]')
    staged = ()
    if control == "apply":
        page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    if control == "withdraw":
        page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
        page.press(f'{_b("fix_hold")} input[data-param="fix_hold"]', "Enter")
        rig.wait_for(lambda: rig.dispatch.seen)
        staged = (Staged("fix_hold", 0.3, 0.5, jake, False, cid=rig.dispatch.seen[-1].cid),)
        _offer(rig, 40, params=_matrix_rows(40), staged=staged)
        _says(rig, page, "fix_hold", "waiting · you")
        page.evaluate("document.activeElement.blur()")
    before = len(rig.dispatch.seen)
    target, name, news = _PRESSED[control]

    page.hover(target)
    page.mouse.down()
    _offer(rig, 41, params=_matrix_rows(41), staged=staged)
    _arrived(page, 41)
    page.mouse.up()
    rig.wait_for(lambda: _head(page, name) == news)
    time.sleep(0.3)  # housekeeping: room for a wrong second send to arrive
    sent = rig.dispatch.seen[before:]

    if control == "field":
        field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
        assert page.evaluate("document.activeElement.getAttribute('data-param')") == "fix_hold"
        assert page.input_value(field) == "0.35", "an untouched field follows the frame"
        assert _say(page, "fix_hold") != "not sent"
        page.fill(field, "0.5")
        page.press(field, "Enter")
        rig.wait_for(lambda: len(rig.dispatch.seen) == before + 1)
        assert [(type(s), s.value) for s in rig.dispatch.seen[before:]] == [(SetParameter, 0.5)]
    elif control == "stepper":
        assert sent == []
        assert page.input_value(f'{_b("set_size")} input[data-param="set_size"]') == "5"
        assert _say(page, "set_size") == "not sent"
    elif control == "segment":
        assert sent == []
        assert page.is_visible(f'{_b("wait")} [data-side="drawn"]')
        assert _say(page, "wait") == "cannot send · wait's shortest needs a number"
    elif control == "tick":
        # The tick pressed stays a draft; the one the frame added follows it, untouched by hand;
        # its Apply sends the pool's number with both.
        assert sent == []
        assert page.is_checked(target) and page.is_checked(
            _b("pairings") + ' input.tick[aria-label="blue among green"]')
        assert _say(page, "pairings") == "not sent"
        page.click(f'{_b("pairings")} [data-apply]')
        rig.wait_for(lambda: len(rig.dispatch.seen) == before + 1)
        (ticked,) = rig.dispatch.seen[before:]
        assert (type(ticked), ticked.name, ticked.value) == (SetParameter, "pairings", 70 + 2048)
    elif control == "swatch":
        assert sent == []
        assert page.get_attribute(target, "aria-pressed") == "true"
        assert _say(page, "distractor_appearance") == "not sent"
        page.click(f'{_b("distractor_appearance")} [data-apply]')
        rig.wait_for(lambda: len(rig.dispatch.seen) == before + 1)
        (picked,) = rig.dispatch.seen[before:]
        assert (type(picked), picked.colorset, picked.color) == (SetColor, "isohue", "red")
    elif control == "apply":
        assert [(type(s), s.name, s.value) for s in sent] == [(SetParameter, "fix_hold", 0.5)]
        assert _say(page, "fix_hold") == "sending…"
    elif control == "withdraw":
        assert [(type(s), s.cid) for s in sent] == [(Withdraw, staged[0].cid)]
    elif control == "line":
        assert sent == [] and _opened(page) == ["set_size"]
        assert page.text_content(target + " > .lv") == "6"
    elif control == "pinned line":
        assert sent == [] and page._page.is_visible(_pinned("set_size"))
        assert page.get_attribute(target, "aria-pressed") == "true"
        assert page.text_content(target + " > .lv") == "6"
    elif control == "pinned stepper":
        assert sent == []
        assert page.input_value(f'{_pinned("set_size")} input[data-param="set_size"]') == "5"
        assert page.input_value(f'{_b("set_size")} input[data-param="set_size"]') == "5"
        assert _say(page, "set_size") == "not sent"
    else:
        assert [(type(s), s.name) for s in sent] == [(HandBack, "gap")]
    for neighbor, shown in (("response_deadline", "0.60 s"), ("set_size", "6 objects"),
                            ("wait", "0.55 s"), ("gap", "0.65 s")):
        assert _head(page, neighbor) == shown, neighbor


def test_tab_reaches_apply_on_every_box(rig):
    """The controls review's F7: in Safari, Tab did not reach a single button on a card (its
    default Tabs to fields and pop-ups only). From a box's field with a draft, Tab reaches that
    box's Discard and then its Apply, on every box, before leaving it: both carry `tabindex="0"`.
    Run in WebKit, where this is the test."""
    page = _task6_page(rig)
    for name, value in (("fix_hold", "0.5"), ("response_deadline", "0.8"), ("set_size", "6"),
                        ("reward_correct", "0.2")):
        field = f'{_b(name)} input[data-param="{name}"]'
        page.fill(field, value)
        page.focus(field)
        reached = []
        for _ in range(2):
            page.keyboard.press("Tab")
            reached.append(page.evaluate(
                "(() => { const at = document.activeElement; const box = at.closest('.box');"
                " return [box ? box.getAttribute('data-card') : null,"
                " at.getAttribute('data-discard') !== null ? 'Discard' :"
                " at.getAttribute('data-apply') !== null ? 'Apply' : at.tagName]; })()"))
        assert reached == [[name, "Discard"], [name, "Apply"]], (name, reached)


def test_drafts_survive_a_tab_switch_and_are_dropped_at_the_runs_end(rig):
    """The design's call: drafts are kept per setting across frames and tab switches, dropped at
    the run's end and on a reload, and closing the page with drafts asks once (`beforeunload`)."""
    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.5")
    page.click('label[for="t-training"]')
    _offer(rig, 41, params=_task6_rows())
    _arrived(page, 41)
    page.click('label[for="t-task"]')

    assert page.input_value(field) == "0.5" and _say(page, "fix_hold") == "not sent"
    asked = []
    page.on("dialog", lambda dialog: (asked.append(dialog.type), dialog.accept()))
    page.reload()
    page.click('label[for="t-task"]')
    assert page.input_value(field) == "0.30" and _bar(page) is None
    assert asked in ([], ["beforeunload"]), asked

    page.fill(field, "0.5")
    page.fill(f'{_b("set_size")} input[data-param="set_size"]', "6")
    page.evaluate("document.activeElement.blur()")
    _offer(rig, 42, params=_task6_rows(), phase="between_runs")
    _arrived(page, 42)
    rig.wait_for(lambda: page.input_value(field) == "0.30")
    assert page.input_value(f'{_b("set_size")} input[data-param="set_size"]') == "4"
    assert "draft" not in _classes(page, "fix_hold") and _bar(page) is None


def test_a_whole_box_refuses_a_point_at_the_keyboard_and_on_paste(rig):
    """The plan's Review Focus 5 and the design's goal 6: a whole setting's field takes no `.` at
    the keyboard, saying so; a fraction that arrives anyway -- pasted, here inserted as a paste
    inserts it, with no key pressed -- is *cannot send · whole numbers only*, its Apply off, Enter
    and Apply all sending nothing."""
    page = _task6_page(rig)
    field = f'{_b("set_size")} input[data-param="set_size"]'
    page.fill(field, "")
    page.type(field, "4.")
    assert page.input_value(field) == "4"
    assert _say(page, "set_size") == "whole numbers only"
    # The whole-build review's I5: the fraction's digits after a refused point are refused too, so
    # "12.5" never reads "125", and what was typed cannot be sent while it stands.
    page.type(field, "5")
    assert page.input_value(field) == "4" and _say(page, "set_size") == "whole numbers only"
    page.fill(field, "")
    page.type(field, "12.5")
    assert page.input_value(field) == "12"
    assert _say(page, "set_size") == "cannot send · whole numbers only"
    assert page.is_disabled(f'{_b("set_size")} [data-apply]')
    page.press(field, "Enter")
    time.sleep(0.3)  # housekeeping: room for a wrong send to arrive
    assert rig.dispatch.seen == []
    page.press(field, "Backspace")
    assert page.input_value(field) == "1" and _say(page, "set_size") == "not sent"
    page.type(field, "5")
    assert page.input_value(field) == "15", "a digit after any other edit is typed"

    page.fill(field, "")
    page.focus(field)
    page.keyboard.insert_text("4.5")
    assert page.input_value(field) == "4.5"
    assert _say(page, "set_size") == "cannot send · whole numbers only"
    assert "cannot" in _classes(page, "set_size")
    assert page.is_disabled(f'{_b("set_size")} [data-apply]')
    page.press(field, "Enter")
    assert _bar(page) == "1 edit not sent: set_size · set_size cannot send: whole numbers only"
    assert page.is_disabled("#drafts-apply")
    time.sleep(0.3)  # housekeeping: room for a wrong send to arrive
    assert rig.dispatch.seen == []


def test_an_act_refused_on_one_box_is_refused_on_every_box_of_it(rig):
    """The controls' ruling (the plan's Review Focus 2): a frame keeps only the last refusals, so a
    large act refused whole may not leave one on every box of it; any refusal carrying the act's
    id refuses all of it. A box of the act with no refusal of its own in the frame says it was
    refused with the changes applied together, its draft back; the one that has its own says it."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Refused

    page = _task6_page(rig)
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.95")
    page.fill(f'{_b("response_deadline")} input[data-param="response_deadline"]', "0.8")
    page.click("#drafts-apply")
    rig.wait_for(lambda: rig.dispatch.seen)
    cid = rig.dispatch.seen[-1].cid
    _offer(rig, 41, params=_task6_rows(), refusals=(Refused(
        "fix_hold", Box("Jake Westerberg"), "'fix_hold' at 0.95 is refused, and the previous "
        "value stands: it does not fit; so none of the 2 applied together is staged", cid=cid,
        value=0.95),))

    _says(rig, page, "response_deadline", "refused · with the changes applied together")
    assert {"refused", "draft"} <= set(_classes(page, "response_deadline"))
    assert page.input_value(f'{_b("response_deadline")} input[data-param="response_deadline"]') == "0.8"
    assert _say(page, "fix_hold").startswith("refused 0.95 · it does not fit")
    assert _bar(page) == "2 edits not sent: fix_hold, response_deadline"


def test_a_box_the_find_box_hides_stays_hidden_while_its_act_is_out(rig):
    """The find box's mark is the page's own (`nofind`), kept when the script brings a box up to
    date: Apply all of a draft the find box now hides leaves it hidden while its act is out."""
    page = _task6_page(rig)
    page.fill(f'{_b("response_deadline")} input[data-param="response_deadline"]', "0.8")
    page.fill("#pfind", "fix_")
    assert not page.is_visible(_b("response_deadline")) and page.is_visible(_b("fix_hold"))
    rig.dispatch.delay = 2.0
    # Pressed and read in one turn of the page's script (the console interface rework's Task 8): a
    # box brought up to date as its act is sent keeps its mark, whatever answers or frames follow.
    assert page.evaluate("(() => { document.getElementById('drafts-apply').click(); return "
                         "document.querySelector('#params .box[data-card=\"response_deadline\"]')"
                         ".classList.contains('nofind'); })()")
    rig.wait_for(lambda: rig.dispatch.seen)

    assert _say(page, "response_deadline") == "sending…"
    assert not page.is_visible(_b("response_deadline")) and page.is_visible(_b("fix_hold"))


# --- the console interface rework's Task 7: the pairings grid, group boxes and percents ---------

#: The pop-out's four colors in its pool's order, each with a swatch as the rig sends one.
_POOL_COLORS = {"blue": "#2476c8", "purple": "#8a5cc2", "red": "#bf5c5c", "green": "#3f9a4a"}


def _pool_row(value=66, **fields):
    """A pool's setting's row as the rig makes it (`taskd.pool_members`): its twelve pairs in the
    pool's order -- blue among purple 1, blue among red 2 ... green among red 2048 -- `on` as
    `value` holds them, in the Colors section."""
    from wl_xcon.link import ParamRow, PoolMember

    pairs = [(odd, among) for odd in _POOL_COLORS for among in _POOL_COLORS if among != odd]
    members = tuple(
        PoolMember(bit=1 << at, odd=odd, among=among, odd_hex=_POOL_COLORS[odd],
                   among_hex=_POOL_COLORS[among], on=bool(value >> at & 1))
        for at, (odd, among) in enumerate(pairs))
    return ParamRow.of("pairings", "pairings", 1.0, 4095.0, value, False, source="run",
                       whole=True, step=1.0, section="Colors", members=members, **fields)


def _tick(name: str) -> str:
    return f'{_b("pairings")} input.tick[aria-label="{name}"]'


def test_pairings_are_a_grid_of_twelve_ticks(rig):
    """The design's goal 7 (the PI, 2026-11-19: "what are pairings?"; "4 × 4 grid, add or
    remove"): the pool's 66 shows as a grid of twelve ticks, blue among red and red among blue
    ticked, the diagonal empty; ticking green among red is a draft, nothing sent, and its Apply
    sends one `set` of the pool's number, 66 + 2048, as the record keeps it; a tick put back is no
    draft; unticking sends less, a pair taken away live as one is added. None ticked cannot be
    sent."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, SetParameter, Staged

    jake = Box("Jake Westerberg")
    page = _task6_page(rig, params=_task6_rows() + (_pool_row(),))

    ticks = page.eval_on_selector_all(
        f'{_b("pairings")} input.tick', "ticks => ticks.map((t) => [t.getAttribute('aria-label'),"
        " Number(t.getAttribute('data-bit')), t.checked])")
    assert len(ticks) == 12 and [bit for _, bit, _ in ticks] == [1 << n for n in range(12)]
    assert [said for said, _, on in ticks if on] == ["blue among red", "red among blue"]
    assert page.eval_on_selector_all(f'{_b("pairings")} td.diag',
                                     "cells => cells.map((c) => c.children.length)") == [0] * 4
    assert _head(page, "pairings") == "2 of 12 pairs"
    assert "wide" in _classes(page, "pairings")

    page.click(_tick("green among red"))
    assert _say(page, "pairings") == "not sent" and rig.dispatch.seen == []
    assert _bar(page) == "1 edit not sent: pairings"
    page.click(_tick("green among red"))
    assert _say(page, "pairings") != "not sent" and _bar(page) is None
    page.click(_tick("green among red"))
    page.click(f'{_b("pairings")} [data-apply]')
    rig.wait_for(lambda: rig.dispatch.seen)
    time.sleep(0.3)  # housekeeping: room for a wrong second send to arrive
    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.value) == (SetParameter, "pairings", 66 + 2048)

    _offer(rig, 41, params=_task6_rows() + (_pool_row(),),
           staged=(Staged("pairings", 66.0, 2114.0, jake, False, cid=sent.cid),))
    _says(rig, page, "pairings", "waiting · you")
    assert _head(page, "pairings") == "2 of 12 pairs → 3 of 12 pairs"
    _offer(rig, 42, params=_task6_rows() + (_pool_row(2114, applied=Applied(42, str(jake))),))
    _says(rig, page, "pairings", "in force from trial 42")
    assert page.is_checked(_tick("green among red"))

    page.click(_tick("blue among red"))
    page.click(_tick("red among blue"))
    page.click(_tick("green among red"))
    assert _say(page, "pairings") == "cannot send · tick at least one pair"
    page.click(_tick("green among red"))
    page.click(f'{_b("pairings")} [data-apply]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    assert (rig.dispatch.seen[-1].name, rig.dispatch.seen[-1].value) == ("pairings", 2048)


def _group_rows(bar=0.8, window=50, **over):
    from wl_xcon.link import ParamRow

    rows = {
        "move_up_bar": ParamRow.of("move_up_bar", "fraction", 0.0, 1.0, bar, False,
                                   source="task", step=0.05, percent=True, label="Bar to move up",
                                   group="Move up", section="Rules"),
        "move_up_window": ParamRow.of("move_up_window", "answers", 1.0, 200.0, window, False,
                                      source="task", whole=True, step=1.0, label="Answers judged",
                                      group="Move up", section="Rules"),
    }
    for name, fields in over.items():
        rows[name] = dataclasses.replace(rows[name], **fields)
    return _task6_rows() + tuple(rows.values())


def _move_up():
    from wl_xcon.link import GroupRow

    return (GroupRow("Move up", ("move_up_bar", "move_up_window"),
                     "Move up when at least {move_up_bar} of the last {move_up_window} answers "
                     "are right", "Rules"),)


def test_a_group_box_applies_its_settings_together(rig):
    """The design's goal 8 and its call "withdraw takes back the whole act": a group's box is one
    box with one Apply -- its sentence with each field in place -- and that Apply sends one
    `apply_many` of the settings it changed under one command id, staged together or refused
    whole; its box says *sending…*, then *waiting · you*, and *withdraw all 2* takes the whole act
    back by that id. A group with one field changed still sends one `apply_many`. Its draft is
    named by the group in the drafts bar, and Apply all carries it."""
    from wl_xcon.actor import Box
    from wl_xcon.link import ApplyMany, SetParameter, Staged, Withdraw

    jake = Box("Jake Westerberg")
    page = _task6_page(rig, params=_group_rows(), groups=_move_up())
    box = _b("Move up")
    assert page.eval_on_selector_all(
        f"{box} .editor .sentence > *",
        "parts => parts.map((p) => p.matches('.gs') ? p.textContent : '[' +"
        " p.querySelector('input').value + ']' + (p.querySelector('.unit') ?"
        " p.querySelector('.unit').textContent : ''))"
    ) == ["Move up when at least ", "[80]%", " of the last ", "[50]", " answers are right"]
    assert page.locator('#params .box[data-card="move_up_bar"]').count() == 0

    page.fill(f'{box} input[data-param="move_up_bar"]', "90")
    page.click(f'{box} input[data-param="move_up_window"] ~ [data-dir="1"]')
    assert _say(page, "Move up") == "not sent" and rig.dispatch.seen == []
    assert _bar(page) == "1 edit not sent: Move up"
    page.click(f"{box} [data-apply]")
    rig.wait_for(lambda: rig.dispatch.seen)
    time.sleep(0.3)  # housekeeping: room for a wrong second send to arrive

    (sent,) = rig.dispatch.seen
    assert type(sent) is ApplyMany and sent.cid
    assert [(type(change), change.name, change.value) for change in sent.changes] == [
        (SetParameter, "move_up_bar", 0.9), (SetParameter, "move_up_window", 51.0)]
    assert _say(page, "Move up") == "sending…"
    staged = (Staged("move_up_bar", 0.8, 0.9, jake, False, cid=sent.cid),
              Staged("move_up_window", 50.0, 51.0, jake, False, cid=sent.cid))
    _offer(rig, 41, params=_group_rows(), groups=_move_up(), staged=staged)
    _says(rig, page, "Move up", "waiting · you")
    assert page.text_content(f"{box} [data-withdraw]") == "withdraw all 2"
    assert _head(page, "Move up") == "80 → 90 % · 50 → 51 answers"
    page.click(f'{box} [data-withdraw="{sent.cid}"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    assert (type(rig.dispatch.seen[-1]), rig.dispatch.seen[-1].cid) == (Withdraw, sent.cid)

    _offer(rig, 42, params=_group_rows(), groups=_move_up(), withdrawals=(sent.cid,))
    _says(rig, page, "Move up", "withdrawn · it never applied")
    page.fill(f'{box} input[data-param="move_up_window"]', "60")
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    assert _bar(page) == "2 edits not sent: fix_hold, Move up"
    page.click(f"{box} [data-apply]")
    rig.wait_for(lambda: len(rig.dispatch.seen) == 3)
    alone = rig.dispatch.seen[-1]
    assert type(alone) is ApplyMany and [(c.name, c.value) for c in alone.changes] == [
        ("move_up_window", 60.0)]
    _offer(rig, 43, params=_group_rows(), groups=_move_up(), staged=(
        Staged("move_up_window", 50.0, 60.0, jake, False, cid=alone.cid),))
    _says(rig, page, "Move up", "waiting · you")
    assert _bar(page) == "1 edit not sent: fix_hold"


def test_a_percent_field_shows_80_and_sends_0_8(rig):
    """The design's call: "a fraction may be shown as a percent ... its steps, limits and the rig's
    sentences are converted on the page, and the setting, the command and the record keep the
    fraction": the bar's 0.8 shows as 80 with `%`, steps by 5 and stops at 100; typed back to 80 it
    is no draft; 80 is sent as 0.8, and 33.3 as 0.333 -- never 0.33299999999999996, the noise of
    33.3 / 100 -- and the value in force comes back as 33.3."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Applied, SetParameter

    jake = Box("Jake Westerberg")
    page = _task6_page(rig, params=_group_rows(), groups=())
    field = f'{_b("move_up_bar")} input[data-param="move_up_bar"]'
    assert page.input_value(field) == "80" and _head(page, "move_up_bar") == "80 %"
    assert page.text_content(f'{_b("move_up_bar")} .editor .unit') == "%"

    page.click(f'{_b("move_up_bar")} [data-dir="1"]')
    assert page.input_value(field) == "85" and _say(page, "move_up_bar") == "not sent"
    page.click(f'{_b("move_up_bar")} [data-dir="1"]', modifiers=["Shift"])
    assert page.input_value(field) == "100"
    page.fill(field, "80")
    assert _say(page, "move_up_bar") != "not sent" and _bar(page) is None
    page.fill(field, "90")
    page.fill(field, "80.0")
    assert _bar(page) is None, "80.0 is the 80 in force"

    page.fill(field, "33.3")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name) == (SetParameter, "move_up_bar")
    assert sent.value == 0.333 and repr(sent.value) == "0.333"
    _offer(rig, 41, params=_group_rows(0.333, move_up_bar={"applied": Applied(41, str(jake))}))
    _says(rig, page, "move_up_bar", "in force from trial 41")
    assert page.input_value(field) == "33.3" and _head(page, "move_up_bar") == "33.3 %"

    page.fill(field, "80")
    page.press(field, "Enter")
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    assert repr(rig.dispatch.seen[-1].value) == "0.8"


# --- the console interface rework's Task 8: the page around the boxes ---------------------------
#
# One bar that stays in view, the find box on both settings tabs, what is not sent counted where a
# person looks, pins to Runtime, the demo's keys folded, and the density that brings the page to
# the mock-up the PI approved (`ui-review/shots/layout/mockup.html`). Through the wire, in a real
# browser: each runs in Chromium in the suite and in WebKit (`WLX_BROWSER=webkit`), for Safari, by
# the builder.

def _rect(page, selector: str) -> dict:
    return page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect();"
                         " return {top: r.top, bottom: r.bottom, left: r.left, right: r.right,"
                         " height: r.height}; }", selector)


def test_the_top_bar_stays_in_view_while_settings_scroll(rig, tmp_path):
    """The design's call: "the top of the page becomes one bar that stays in view: state, trial,
    correct, fluid, cage time and the run's buttons; the session's details behind a *session*
    button" (the layout review's finding 4: *stop run*, *give reward* and the trial count scrolled
    away). At 1280 × 800 on the Task parameters tab, scrolled to its foot, the bar is still at the
    top of the window with the trial, the right answers, the fluid and the cage time, and the run's
    buttons in it; *stop run* there opens its confirm in view and sends nothing; the session's
    details are behind *session* on the settings tabs and shown on Runtime."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_frame(tmp_path, trial_index=9))))
    page = rig.browser_page()
    _sign_in(page)
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    assert page.is_visible("#head-id") and page.get_attribute("#session-btn", "aria-expanded") == "true"
    page.click('label[for="t-task"]')
    page.wait_for_selector("#params > .summary .line", state="visible")
    assert not page.is_visible("#head-id"), "the session's details are behind *session* here"
    assert page.get_attribute("#session-btn", "aria-expanded") == "false"
    # A tall setting opened, its reasons and its draw's profile shown, so the page runs past the
    # window (rewritten for the summary and editor design of 2026-11-19: one box is shown).
    _open(page, "fix_hold")
    page.click(f'{_b("fix_hold")} > details.more > summary')

    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    # One box shown, not the grid's twenty, so the page runs less far past the window than it did.
    assert page.evaluate("window.scrollY") > 100, "the settings scroll"
    bar = _rect(page, "#bar")
    assert abs(bar["top"]) < 1 and bar["bottom"] < 100, bar
    said = " ".join(page.text_content("#bar-nums").split())
    for word in ("trial 9", "correct", "fluid today", "cage"):
        assert word in said, (word, said)
    for cmd in ("pause", "mark", "reward", "stop"):
        button = _rect(page, f'#bar [data-cmd="{cmd}"]')
        assert bar["top"] <= button["top"] and button["bottom"] <= bar["bottom"], cmd
    last = page.evaluate("document.querySelector('#params > .editing > .box:not([hidden])')"
                         ".getBoundingClientRect().bottom")
    assert last <= LAPTOP_H + 1, "the opened box is scrolled up under the bar"

    page.click('#bar [data-cmd="stop"]')
    confirm = _rect(page, "#stop-confirm")
    assert page.is_visible("#stop-confirm") and 0 <= confirm["top"] and confirm["bottom"] <= LAPTOP_H
    page.click("#stop-no")
    page.click("#session-btn")
    assert page.is_visible("#head-id") and page.is_visible("#task-sel")
    assert page.get_attribute("#session-btn", "aria-expanded") == "true"
    page.click("#session-btn")
    assert not page.is_visible("#head-id")
    page.click('label[for="t-runtime"]')
    assert page.is_visible("#head-id"), "shown on Runtime"
    assert rig.dispatch.seen == []


def _found(page, root: str = "#params") -> list:
    """The summary lines the find box leaves undimmed, by the setting each opens (rewritten for
    the summary and editor design of 2026-11-19: the boxes are in the editor, one shown)."""
    return page.eval_on_selector_all(
        f"{root} > .summary .line[data-open]:not(.nofind):not(.newcolor)",
        "lines => lines.map((line) => line.getAttribute('data-open'))")


def test_find_matches_a_plain_name_a_code_name_and_a_section(rig):
    """The design's goal 5 ("the find box matches both, and section names") and the ledger's find
    ruling for Task 8: on both settings tabs, the find box finds a box by its plain name, its code
    name, or the name of a section it stands in -- a parent's finding its subsections' boxes -- and
    a group's box by its title and by each of its settings' plain and code names; each tab's box
    finds on its own tab alone; cleared, every box is shown again."""
    from wl_xcon.link import ParamRow

    rows = _group_rows() + (
        ParamRow.of("fix_window", "deg", 0.0, 9.0, 2.0, False, label="Fixation window",
                    section="Gaze windows"),
        ParamRow.of("fix_size", "deg", 0.0, 9.0, 0.5, False, section="Stimuli/fixation point"),
        ParamRow.of("move_back_bar", "fraction", 0.0, 1.0, 0.5, False, label="Bar to move back",
                    section="Training"),
        ParamRow.of("crowd_step", "objects", 1.0, 10.0, 1.0, False, whole=True, step=1.0,
                    section="Training/staircases"),
    )
    rows = tuple(dataclasses.replace(row, label="Fixation hold") if row.name == "fix_hold" else row
                 for row in rows)
    page = _task6_page(rig, params=rows, groups=_move_up())
    every = _found(page)
    assert {"fix_hold", "Move up", "fix_window", "fix_size", "set_size"} <= set(every)

    page.fill("#pfind", "fix_win")
    assert page.is_visible('#params > .summary .line[data-open="set_size"]'), (
        "a line not found is dimmed, not hidden (the summary and editor design's goal 8)")
    for typed, found in (("fixation hold", ["fix_hold"]), ("FIX_WIN", ["fix_window"]),
                         ("stimuli", ["set_size", "fix_size"]),
                         ("fixation point", ["fix_size"]), ("gaze", ["fix_window"]),
                         ("move up", ["Move up"]), ("answers judged", ["Move up"]),
                         ("move_up_window", ["Move up"]), ("rules", ["Move up"])):
        page.fill("#pfind", typed)
        assert _found(page) == found, typed
    page.click('label[for="t-training"]')
    assert set(_found(page, "#training-params")) == {"move_back_bar", "crowd_step"}, (
        "the Task parameters tab's find box finds there alone")
    for typed, found in (("bar to move back", ["move_back_bar"]), ("crowd_st", ["crowd_step"]),
                         ("staircases", ["crowd_step"]),
                         ("training", ["move_back_bar", "crowd_step"])):
        page.fill("#tfind", typed)
        assert _found(page, "#training-params") == found, typed
    page.fill("#tfind", "")
    page.click('label[for="t-task"]')
    page.fill("#pfind", "")
    assert _found(page) == every


def test_a_section_and_its_tab_count_the_edits_not_sent(rig):
    """The console interface rework's Task 8: each section's header counts what in it is not sent
    after the rig's counts ("Timing · 2 settings · 1 not sent"), a group's settings
    each once and a parent taking in its subsections, and each settings tab's label says how many
    while any exists; a frame keeps them, and Discard all clears them, leaving the rig's counts
    as they were."""
    from wl_xcon.link import ParamRow

    rows = _group_rows() + (
        ParamRow.of("crowd_step", "objects", 1.0, 10.0, 1.0, False, whole=True, step=1.0,
                    section="Training/staircases"),)
    page = _task6_page(rig, params=rows, groups=_move_up())

    def header(name, root="#params"):
        # The summary's section header (the summary and editor design of 2026-11-19).
        return " ".join(page.text_content(
            f'{root} .ssec[data-section="{name}"] > h4, '
            f'{root} .ssec[data-section="{name}"] > .skeep > h4').split())

    def tab(which):
        return " ".join(page.text_content(f'label[for="{which}"]').split())

    assert (header("Timing"), tab("t-task")) == ("Timing · 2 settings", "Task parameters")
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    assert header("Timing") == "Timing · 2 settings · 1 not sent"
    assert tab("t-task") == "Task parameters · 1 not sent"
    page.fill(f'{_b("response_deadline")} input[data-param="response_deadline"]', "0.8")
    page.fill(f'{_b("Move up")} input[data-param="move_up_bar"]', "90")
    page.fill(f'{_b("Move up")} input[data-param="move_up_window"]', "51")
    assert header("Timing") == "Timing · 2 settings · 2 not sent"
    assert header("Rules") == "Rules · 2 settings · 2 not sent"
    assert header("Stimuli") == "Stimuli · 1 setting"
    assert tab("t-task") == "Task parameters · 4 not sent"
    page.click('label[for="t-training"]')
    page.fill(f'{_b("crowd_step", "#training-params")} input[data-param="crowd_step"]', "2")
    assert header("Training", "#training-params") == "Training · 1 setting · 1 not sent"
    assert header("Training/staircases", "#training-params") == (
        "staircases · 1 setting · 1 not sent")
    assert tab("t-training") == "Training · 1 not sent"
    _offer(rig, 41, params=rows, groups=_move_up())
    _arrived(page, 41)
    page.click('label[for="t-task"]')
    assert header("Timing") == "Timing · 2 settings · 2 not sent"
    page.click(f'{_b("fix_hold")} [data-discard]')
    assert header("Timing") == "Timing · 2 settings · 1 not sent"

    page.click("#drafts-discard")
    assert (header("Timing"), header("Rules"), tab("t-task"), tab("t-training")) == (
        "Timing · 2 settings", "Rules · 2 settings", "Task parameters",
        "Training")
    assert rig.dispatch.seen == []


#: Each text of a box that is cut short where it is drawn (`scrollWidth` past `clientWidth`): what
#: a person reads is what fits, so a test that reads `textContent` cannot tell (the whole-build
#: review's I4).
_CUT = """(selector) => Array.from(document.querySelectorAll(selector)).filter(
    (node) => node.scrollWidth > node.clientWidth + 0.5).map(
    (node) => [node.closest('.box').getAttribute('data-card'), node.className, node.textContent,
               node.scrollWidth, node.clientWidth])"""


def test_a_waiting_box_shows_what_waits_and_for_whom_at_three_widths(rig):
    """The whole-build review's I4: a box waiting for the next trial -- this page's change and
    another console's, beside *withdraw* -- shows the value in force and what waits in its head
    ("0.30 → 0.50 s") and who sent it on its status line, nothing of either cut short, at 1024, 1280
    and 1440 wide; and its height is its height at rest, its field where it was. Run in WebKit too,
    for Safari."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Staged

    jake, kim = Box("Jake Westerberg"), Box("Kim")
    rows = _task6_rows(fix_hold={"label": "Fixation hold, before the array is shown"})
    _offer(rig, 40, params=rows)
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    page.wait_for_selector(_b("fix_hold"), state="visible")
    names = ("fix_hold", "response_deadline", "set_size")

    def measured():
        return [(round(_rect(page, _b(name))["height"], 1),
                 round(_rect(page, f'{_b(name)} input[data-param="{name}"]')["top"], 1))
                for name in names]

    rests = {}
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": LAPTOP_H})
        rests[width] = measured()
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    page.click(f'{_b("fix_hold")} [data-apply]')
    rig.wait_for(lambda: rig.dispatch.seen)
    mine = rig.dispatch.seen[-1].cid
    _offer(rig, 41, params=rows, staged=(
        Staged("fix_hold", 0.3, 0.5, jake, False, cid=mine),
        Staged("response_deadline", 0.6, 0.85, kim, False, cid="other-1"),
        Staged("set_size", 4, 12, kim, False, cid="other-2")))
    _says(rig, page, "fix_hold", "waiting · you")
    _says(rig, page, "response_deadline", "waiting · Kim", start=True)
    assert page.get_attribute(f'{_b("fix_hold")} > .status > .say', "title") == (
        "waiting for the next trial · you")
    assert _head(page, "fix_hold") == "0.30 → 0.50 s"
    assert _head(page, "response_deadline") == "0.60 → 0.85 s"
    assert _head(page, "set_size") == "4 → 12 objects"
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": LAPTOP_H})
        cut = page.evaluate(_CUT, "#params .box.staged > .head .now, #params .box.staged > .status > .say")
        assert cut == [], (width, cut)
        assert measured() == rests[width], (width, "waiting")


def test_a_box_keeps_its_height_as_its_status_changes(rig):
    """The design's anti-goal ("a box whose height jumps as its status changes, moving Apply under
    the pointer") under the ledger's density ruling for Task 8: the head says the value in force
    only while it differs from the field, and a plain name wraps rather than being cut, so a box
    must keep its height and its field's place as it goes from rest to *not sent* (its head now
    saying the value in force), *sending…*, *waiting* (the head saying what waits, *withdraw*
    offered) and *refused*. At 1280 × 800, a box with the longest plain name and one without."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Refused, Staged

    jake = Box("Jake Westerberg")
    rows = _task6_rows(fix_hold={"label": "Fixation hold, before the array is shown"})
    _offer(rig, 40, params=rows)
    page = rig.browser_page()
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    _sign_in(page)
    page.click('label[for="t-task"]')
    page.wait_for_selector(_b("fix_hold"), state="visible")
    rig.dispatch.delay = 0.5  # housekeeping: long enough to measure *sending…*

    def measured():
        # Each opened in the editor in turn, measured where it stands (rewritten for the summary
        # and editor design of 2026-11-19, which shows one box at a time).
        found = []
        for name in ("fix_hold", "response_deadline"):
            _open(page, name)
            found.append((round(_rect(page, _b(name))["height"], 1),
                          round(_rect(page, f'{_b(name)} input[data-param="{name}"]')["top"], 1)))
        return found

    rest = measured()
    for name, value in (("fix_hold", "0.5"), ("response_deadline", "0.8")):
        page.fill(f'{_b(name)} input[data-param="{name}"]', value)
    assert _say(page, "fix_hold") == "not sent" and _head(page, "fix_hold") == "0.30 s"
    assert page.is_visible(f'{_b("fix_hold")} > .head .now')
    assert measured() == rest, "not sent"
    page.click(f'{_b("fix_hold")} [data-apply]')
    page.click(f'{_b("response_deadline")} [data-apply]')
    _says(rig, page, "fix_hold", "sending…")
    assert measured() == rest, "sending"
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    first, second = (sent.cid for sent in rig.dispatch.seen)
    _offer(rig, 41, params=rows,
           staged=(Staged("fix_hold", 0.3, 0.5, jake, False, cid=first),
                   Staged("response_deadline", 0.6, 0.8, jake, False, cid=second)))
    _says(rig, page, "fix_hold", "waiting · you")
    assert _head(page, "fix_hold") == "0.30 → 0.50 s"
    assert measured() == rest, "waiting"
    applied = _task6_rows(0.5, 0.8, fix_hold={"label": "Fixation hold, before the array is shown"})
    _offer(rig, 42, params=applied, refusals=(
        Refused("fix_hold", jake, _LONG_WHY, cid="box-9", value=30.0),
        Refused("response_deadline", jake, _LONG_WHY, cid="box-8", value=3.0)))
    _says(rig, page, "fix_hold", "refused", start=True)
    assert measured() == rest, "refused"


#: **`localStorage` blocked**, as a private window or blocked site data leave it: reading the store
#: itself throws. `sessionStorage`, which holds the sign-in, is left alone.
_NO_LOCAL_STORE = ("Object.defineProperty(window, 'localStorage', { configurable: true,"
                   " get() { throw new Error('storage is blocked'); } });")


def _pinned(name: str) -> str:
    """A pinned setting's box in Runtime's editor (the summary and editor build's Task 3)."""
    return f'#pinned-editing > .box[data-pin="{name}"]'


def test_nothing_is_pinned_at_first(rig):
    """The design's goal 9 (the PI, 2026-11-19: "Yes, you choose only"): nothing is pinned until a
    person pins it -- Runtime's Pinned strip hidden, holding no line and its editor no box, every
    box's *more* offering *pin to Runtime*, and nothing kept in the store. In a real browser: run
    with `WLX_BROWSER=webkit` too, for Safari."""
    page = _task6_page(rig)
    page.click('label[for="t-runtime"]')
    assert not page.is_visible("#pinned-pane")
    assert page.locator("#pinned .line").count() == 0
    assert page.locator("#pinned-editing .box").count() == 0
    toggles = page.eval_on_selector_all("#params [data-pin-toggle]", "(all) => all.map((b) => [b.textContent, b.getAttribute('aria-pressed')])")
    assert len(toggles) == 4 and set(map(tuple, toggles)) == {("pin to Runtime", "false")}, toggles
    assert page.evaluate("window.localStorage.getItem('wlx.pins.tasks/fixation_detection.py')") is None


def _pin_line(name: str) -> str:
    """A pinned setting's summary line on Runtime (the summary and editor build's Task 3)."""
    return f'#pinned > .line[data-open="{name}"]'


def test_a_pinned_line_opens_the_editor_on_runtime_and_survives_a_reload(rig):
    """The summary and editor design's goal 9: "Runtime's Pinned strip is a short summary of the
    pinned settings, and a click opens the same editor on Runtime (one editor per tab, the
    setting's one draft shared)". A box's *pin to Runtime*, in its *more*, puts the setting's line
    in the strip (`#pinned` holds lines, not boxes), shown whatever its tab's find box dims; a
    click on it opens the setting's box in Runtime's own editor, as a mirror of the setting's one
    box (the ledger's pin ruling: "one draft per setting, never two diverging copies"). A draft
    made on Runtime shows ● on its Task parameters line too, and back; Esc, Esc returns to the
    pinned line; −/+, Apply from Runtime sends once, *withdraw*; the pin and the setting opened on
    Runtime are kept per task across a reload, and *unpin* takes both away. Rewrites
    `test_a_pinned_box_works_on_runtime_and_survives_a_reload`, whose copy stood in the strip.
    In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.actor import Box
    from wl_xcon.link import SetParameter, Staged, Withdraw

    jake = Box("Jake Westerberg")
    page = _task6_page(rig)
    assert page.text_content(f'{_b("fix_hold")} [data-pin-toggle]') == "pin to Runtime"
    page.click(f'{_b("fix_hold")} > details.more > summary')
    page.click(f'{_b("fix_hold")} [data-pin-toggle]')
    assert page.text_content(f'{_b("fix_hold")} [data-pin-toggle]') == "unpin from Runtime"
    page.click(f'{_b("fix_hold")} > details.more > summary')

    page.fill("#pfind", "set_size")
    page.click('label[for="t-runtime"]')
    line = _pin_line("fix_hold")
    copy = _pinned("fix_hold")
    field = f'{copy} input[data-param="fix_hold"]'
    assert page.locator("#pinned > *").count() == 1 and page.is_visible(line)
    assert "nofind" not in page.get_attribute(line, "class").split(), (
        "a pinned line is shown whatever its tab's find box dims")
    assert page.text_content(f"{line} > .ln") == "fix_hold"
    assert page.text_content(f"{line} > .lv") == "0.30 s"
    assert page.locator("#pinned-editing > .box").count() == 1, "the strip holds lines, the editor one box"
    assert page._page.is_hidden(copy), "closed until its line is clicked"
    assert page.inner_text("#pinned-editing > .placeholder") == web.PINNED_EMPTY
    widths = page.evaluate("""() => [getComputedStyle(document.getElementById('pinned')).columnWidth,
        getComputedStyle(document.querySelector('#params > .summary')).columnWidth]""")
    assert widths[0] == widths[1] and widths[0].endswith("px"), (widths, "its tab's columns")
    page._page.click(line)
    assert page._page.is_visible(copy) and page.is_hidden("#pinned-editing > .placeholder")
    assert page.get_attribute(line, "aria-pressed") == "true"
    assert page.locator('[data-card="fix_hold"]').count() == 1, "one box by the setting's name"

    page.fill(field, "0.50")
    assert page.text_content(f"{copy} > .status > .say").strip() == "not sent"
    assert _bar(page) == "1 edit not sent: fix_hold"
    assert _marked(page, "fix_hold", "#pinned")[:2] == ("●", "0.30 → 0.50 s"), "Runtime's line"
    page.click('label[for="t-task"]')
    assert _marked(page, "fix_hold")[:2] == ("●", "0.30 → 0.50 s"), "the Task parameters line too"
    page.fill("#pfind", "")
    original = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    assert page.input_value(original) == "0.50" and _say(page, "fix_hold") == "not sent"
    page.fill(original, "0.55")
    page.click('label[for="t-runtime"]')
    assert page.input_value(field) == "0.55", "the copy follows its box's draft"
    assert _marked(page, "fix_hold", "#pinned")[:2] == ("●", "0.30 → 0.55 s"), "and its line"
    page.press(field, "Escape")
    assert page.input_value(field) == "0.30"
    assert page.text_content(f"{copy} > .status > .say").strip() == "0.10 to 1.00"
    assert _bar(page) is None and _marked(page, "fix_hold", "#pinned")[:2] == ("", "0.30 s")
    page.press(field, "Escape")
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.matches('#pinned > .line[data-open=\"fix_hold\"]')"), (
        "a second Esc returns to the pinned line")
    page.click(f'{copy} [data-dir="1"]')
    assert page.input_value(field) == "0.35"
    page.click(f"{copy} [data-apply]")
    rig.wait_for(lambda: rig.dispatch.seen)
    page.wait_for_timeout(300)  # housekeeping: room for a second send, were there one
    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.value) == (SetParameter, "fix_hold", 0.35)
    _offer(rig, 41, params=_task6_rows(), staged=(Staged("fix_hold", 0.3, 0.35, jake, False,
                                                         cid=sent.cid),))
    _arrived(page, 41)
    rig.wait_for(lambda: page.text_content(f"{copy} > .status > .say").strip() ==
                 "waiting · you")
    assert _marked(page, "fix_hold", "#pinned")[:2] == ("◷", "0.30 → 0.35 s")
    page.click(f'{copy} [data-withdraw="{sent.cid}"]')
    rig.wait_for(lambda: len(rig.dispatch.seen) == 2)
    assert (type(rig.dispatch.seen[-1]), rig.dispatch.seen[-1].cid) == (Withdraw, sent.cid)

    _offer(rig, 42, params=_task6_rows(), withdrawals=(sent.cid,))
    # Another setting opened on the Task parameters tab: Runtime's editor keeps its own.
    page.click('label[for="t-task"]')
    _open(page, "set_size")
    page.click('label[for="t-runtime"]')
    page.reload()
    page.wait_for_selector(SIGNED_IN, timeout=WAIT_S * 1000)
    page._page.wait_for_selector(copy, state="visible")
    assert page.get_attribute(line, "aria-pressed") == "true"
    assert page.evaluate("window.localStorage.getItem('wlx.pinned-opened.tasks/"
                         "fixation_detection.py')") == "fix_hold"
    assert _opened(page) == ["set_size"], "the Task parameters tab's own"
    assert page.input_value(field) == "0.30"
    page.click(f"{copy} > details.more > summary")
    page.click(f"{copy} [data-pin-toggle]")
    assert not page.is_visible("#pinned-pane")
    assert page.locator("#pinned > *").count() == 0 and page.locator("#pinned-editing .box").count() == 0
    page.reload()
    page.wait_for_selector("#params .box", state="attached")
    assert page.locator("#pinned > *").count() == 0 and page.locator("#pinned-editing .box").count() == 0


def test_a_pinned_line_says_a_refusal_and_its_editor_opens_one_at_a_time(rig):
    """The summary and editor design's goal 9 with two pins: Runtime's editor shows one pinned
    setting at a time, the line clicked; a draft left in one survives opening the other, its line
    keeping ●; a refusal the rig says is on the pinned line as on its tab's (`!`); and a pin of a
    setting no longer among the task's drops its line, its box and what Runtime had open.
    In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Refused

    page = _task6_page(rig)
    _pin(page, "fix_hold")
    _pin(page, "set_size")
    page.click('label[for="t-runtime"]')
    assert page.eval_on_selector_all("#pinned > .line", "(all) => all.map((l) => l.getAttribute('data-open'))") == [
        "fix_hold", "set_size"], "in the order pinned"
    page._page.click(_pin_line("fix_hold"))
    page.fill(f'{_pinned("fix_hold")} input[data-param="fix_hold"]', "0.40")
    page._page.click(_pin_line("set_size"))
    assert page._page.is_visible(_pinned("set_size")) and page._page.is_hidden(_pinned("fix_hold"))
    assert page.get_attribute(_pin_line("fix_hold"), "aria-pressed") == "false"
    assert _marked(page, "fix_hold", "#pinned")[:2] == ("●", "0.30 → 0.40 s")
    page.click("#drafts-discard")
    _offer(rig, 41, params=_task6_rows(), refusals=(
        Refused("set_size", Box("Jake Westerberg"), "'set_size' at 40 is above its 36", value=40.0),))
    _arrived(page, 41)
    rig.wait_for(lambda: _marked(page, "set_size", "#pinned")[0] == "!")
    assert _marked(page, "set_size", "#pinned") == _marked(page, "set_size"), "as its tab's line"
    _offer(rig, 42, params=tuple(row for row in _task6_rows() if row.name != "set_size"))
    _arrived(page, 42)
    rig.wait_for(lambda: page.locator("#pinned > .line").count() == 1)
    assert page.locator("#pinned-editing > .box").count() == 1
    assert page.is_visible("#pinned-editing > .placeholder"), "what Runtime had open is gone"
    assert page.evaluate("window.localStorage.getItem('wlx.pinned-opened.tasks/"
                         "fixation_detection.py')") is None, "and is no longer kept"


def _pin(page, name: str) -> None:
    page.click(f'{_b(name)} > details.more > summary')
    page.click(f'{_b(name)} [data-pin-toggle]')
    page.click(f'{_b(name)} > details.more > summary')


def test_a_pinned_copys_tick_segment_and_swatch_work_as_its_box(rig):
    """The whole-build review's I3 (the design's goal 9: a pinned copy works the same way): a tick
    in a pinned pairings grid ticks it -- the copy and its box both, a draft on the box, its Apply
    sending the pool's number with it -- as a segment of a pinned switch and a pinned swatch do.
    Run in WebKit too, for Safari."""
    from wl_xcon.link import SetParameter

    page = _task6_page(rig, params=_matrix_rows(40))
    for name in ("pairings", "wait", "distractor_appearance"):
        _pin(page, name)
    page.click('label[for="t-runtime"]')
    tick = f'{_pinned("pairings")} input.tick[aria-label="green among red"]'
    page.wait_for_selector(tick, state="visible")

    page.click(tick)
    assert page.is_checked(tick), "the copy's tick stays ticked"
    assert page.is_checked(_tick("green among red")), "its box is ticked"
    assert page.text_content(f'{_pinned("pairings")} > .status > .say').strip() == "not sent"
    page.click(f'{_pinned("wait")} [data-switch="drawn"]')
    assert page.is_visible(f'{_pinned("wait")} [data-side="drawn"]')
    page.click(f'{_pinned("distractor_appearance")} .hue[data-color="red"]')
    assert page.get_attribute(f'{_pinned("distractor_appearance")} .hue[data-color="red"]',
                              "aria-pressed") == "true"
    assert _bar(page).startswith("3 edits not sent: wait, distractor_appearance, pairings")
    page.click(tick)
    assert not page.is_checked(tick) and not page.is_checked(_tick("green among red"))
    page.click(tick)
    page.click(f'{_pinned("pairings")} [data-apply]')
    rig.wait_for(lambda: rig.dispatch.seen)
    (sent,) = rig.dispatch.seen
    assert (type(sent), sent.name, sent.value) == (SetParameter, "pairings", 66 + 2048)


def test_leaving_a_pinned_copys_field_ends_a_refused_points_fraction(rig):
    """The fix wave's re-review, M-a: a point refused in a pinned copy of a whole box refuses the
    digits after it, as in the box; leaving the copy's field ends that, as leaving the box's own
    does, so the box's draft can be sent again (its note kept until the box's news or value moves).
    Run in WebKit too, for Safari."""
    page = _task6_page(rig)
    _pin(page, "set_size")
    page.click('label[for="t-runtime"]')
    copy = _pinned("set_size")
    field = f'{copy} input[data-param="set_size"]'
    page.wait_for_selector(field, state="visible")
    page.fill(field, "")
    page.type(field, "12.5")
    assert page.input_value(field) == "12"
    assert page.text_content(f"{copy} > .status > .say").strip() == "cannot send · whole numbers only"
    assert page.is_disabled(f"{copy} [data-apply]")
    page.mouse.click(2, 2)  # a neutral spot: the copy's field loses focus
    rig.wait_for(lambda: not page.is_disabled(f"{copy} [data-apply]"))
    assert page.text_content(f"{copy} > .status > .say").strip() == "whole numbers only"
    assert not page.is_disabled(f'{_b("set_size")} [data-apply]'), "the box's own Apply too"


def test_a_pin_with_its_store_blocked_lasts_the_page_and_nothing_breaks(rig):
    """The design's goal 9 with `localStorage` failing (a private window, blocked site data):
    every access is inside `try`, so a pin still works for as long as the page is shown, nothing
    is raised into the page, and after a reload nothing is pinned."""
    page = _task6_page(rig)
    page.add_init_script(_NO_LOCAL_STORE)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.reload()
    page.wait_for_selector(SIGNED_IN, timeout=WAIT_S * 1000)
    page.click('label[for="t-task"]')
    page.click(f'{_b("set_size")} > details.more > summary')
    page.click(f'{_b("set_size")} [data-pin-toggle]')
    page.click('label[for="t-runtime"]')
    page.click(f'{_pinned("set_size")} [data-dir="1"]')
    assert page.input_value(f'{_pinned("set_size")} input[data-param="set_size"]') == "5"
    assert _bar(page) == "1 edit not sent: set_size"
    page.click("#drafts-discard")
    page.reload()
    page.wait_for_selector("#params .box", state="attached")
    assert page.locator("#pinned-editing .box").count() == 0 and not page.is_visible("#pinned-pane")
    assert errors == [], errors


def test_the_demo_keys_fold_after_the_first_visit(rig):
    """The design's call: "the demo's key list and caveats fold to one line ("keys and demo
    limits"), open on the first visit only" (the layout review's finding 4: 1,326 px on every
    tab). Pages that showed no demo -- two loads of one -- do not use up the first visit; the first demo
    screen this browser shows has them open, a reload has them folded to their one line, and a
    click opens them. With the store blocked every visit is a first: open."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(frame())))
    page = rig.browser_page()
    for _ in range(2):
        page.wait_for_selector("#head-id [data-trial]", state="attached")
        assert not page.is_visible("#demo-pane")
        page.reload()
    rig.hub.offer(decode(encode(frame(demo=True, trial_index=41))))
    page.wait_for_selector("#demo-pane", state="visible")
    assert page.text_content("#demo-fold > summary") == "keys and demo limits"
    assert page.evaluate("document.getElementById('demo-fold').open") is True
    assert page.is_visible("#demo-keys .demo-limits")

    page.reload()
    page.wait_for_selector("#demo-pane", state="visible")
    assert page.evaluate("document.getElementById('demo-fold').open") is False
    assert not page.is_visible("#demo-keys .demo-limits")
    fold = _rect(page, "#demo-fold")
    assert fold["height"] < 2 * 20, "one line"
    page.click("#demo-fold > summary")
    assert page.is_visible("#demo-keys .demo-limits")

    blocked = rig.browser_page()
    blocked.add_init_script(_NO_LOCAL_STORE)
    for _ in range(2):
        blocked.reload()
        blocked.wait_for_selector("#demo-pane", state="visible")
        assert blocked.evaluate("document.getElementById('demo-fold').open") is True


# **The summary and editor build's Task 2: what only the page knows, on the lines; find and the
# keyboard.**


def _line(name: str, root: str = "#params") -> str:
    """A setting's summary line on a settings tab, or (`root` "#pinned") its pinned line on
    Runtime, which stands in a summary of its own (the build's Task 3)."""
    if root == "#pinned":
        return _pin_line(name)
    return f'{root} > .summary .line[data-open="{name}"]'


def _marked(page, name: str, root: str = "#params") -> tuple:
    """A summary line's marks, its value and its title, as the page shows them."""
    return tuple(page.evaluate(
        "(s) => { const l = document.querySelector(s); return [l.querySelector('.mk').textContent,"
        " l.querySelector('.lv').textContent, l.getAttribute('title')]; }", _line(name, root)))


def _popout_started(tmp_path, **over):
    """`_popout_frame` with each setting that holds no value yet at its task's start (the pop-out's
    `Param.start`), as a run shows them: the values a line says, and so how much of its width
    they take."""
    import importlib.util

    from _demo import POPOUT, xtasks_or_skip

    made = _popout_frame(tmp_path, **over)
    spec = importlib.util.spec_from_file_location("popout_started", xtasks_or_skip() / POPOUT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    starts = {param.name: param.start for param in module.TASK.params}
    return dataclasses.replace(made, params=tuple(
        dataclasses.replace(row, value=starts[row.name])
        if row.value is None and isinstance(starts.get(row.name), (int, float)) else row
        for row in made.params))


def test_no_popout_name_is_cut_at_1280(rig, tmp_path):
    """The ledger's ruling for the summary and editor build's Task 2, on the Task 1 screenshot at
    1280 × 800 ("Time to find the fixation…", "Ring distance from cen…", "Disc wind… 0.0 × disc
    radi…"): no plain name of the pop-out's Task parameters is cut short -- at 1280 × 800 with the
    demo screen's column shown, its settings at their start values, and every line still above
    the fold -- nor at 1024 or 1440 wide. The columns are as wide as the longest plain name a task
    may declare with a value beside it, and the summary says "°" and "cd/m²". Through the wire, in
    a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_started(tmp_path, demo=True))))
    page = rig.browser_page()
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    page.click('label[for="t-task"]')
    page.wait_for_selector("#params .box", state="attached")
    assert page.is_visible("#demo-pane"), "the demo screen's column is shown"
    said = dict(page.eval_on_selector_all("#params > .summary .line[data-open]", """lines =>
        lines.map((line) => [line.getAttribute('data-open'), line.querySelector('.lv').textContent])"""))
    assert said["fix_hold"] == "0.5–1.25 s" and said["ring_radius"] == "8.0°", said
    assert said["fix_luminance"] == "40 cd/m²", said
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": LAPTOP_H})
        cut = page.eval_on_selector_all("#params > .summary .line > .ln", """names => names.filter(
            (name) => name.scrollWidth > name.clientWidth + 0.5).map((name) => name.textContent)""")
        assert cut == [], (width, cut)
        if width == 1280:
            below = page.eval_on_selector_all("#params > .summary .line", """lines => lines.filter(
                (line) => line.getBoundingClientRect().bottom + window.scrollY > 800).map(
                (line) => line.getAttribute('data-open'))""")
            assert below == [], below


def test_a_draft_survives_opening_another_and_its_line_says_so(rig):
    """The summary and editor design's goal 4 and its anti-goal ("a trainer who believes an unsent
    edit is in force"): a value typed in one setting, then another opened, the first's box hidden
    keeps the draft, and its line says so -- ● after the name, the value in force and then the
    draft, "0.30 → 0.50 s", *not sent* in its title -- across a frame; the drafts bar names it, and
    Apply all sends it, the line then saying … *sending…*. In a real browser: run with
    `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import ApplyMany

    page = _task6_page(rig)
    rest = _marked(page, "fix_hold")
    assert rest == ("", "0.30 s", "fix_hold · 0.30 s"), rest
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.50")
    _open(page, "set_size")
    assert _opened(page) == ["set_size"]
    assert _marked(page, "fix_hold") == ("●", "0.30 → 0.50 s", "fix_hold · 0.30 → 0.50 s · not sent")
    assert "draft" in page.get_attribute(_line("fix_hold"), "class").split()
    _offer(rig, 41, params=_task6_rows())
    _arrived(page, 41)
    assert _marked(page, "fix_hold")[:2] == ("●", "0.30 → 0.50 s")
    assert _marked(page, "set_size") == ("", "4", "set_size · 4"), "a line with no draft as drawn"
    assert _bar(page) == "1 edit not sent: fix_hold"

    page.click("#drafts-apply")
    rig.wait_for(lambda: rig.dispatch.seen)
    (sent,) = rig.dispatch.seen
    assert type(sent) is ApplyMany
    assert [(change.name, change.value) for change in sent.changes] == [("fix_hold", 0.5)]
    mark, value, title = _marked(page, "fix_hold")
    assert (mark, value) == ("…", "0.30 → 0.50 s") and "sending…" in title.split(" · ")


def test_a_draft_over_a_waiting_change_shows_both_marks(rig):
    """The plan's Review Focus 3: a draft typed over a change already waiting for the next trial
    shows ●◷, the arrow's value the draft's, and its title says both -- *not sent* with who is
    changing it, and the waiting change with who sent it; discarded, the line is the rig's again,
    word for word. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Staged

    page = _task6_page(rig, staged=(Staged("fix_hold", 0.3, 0.6, Box("Ana"), False, cid="other-1"),))
    rig_line = _marked(page, "fix_hold")
    assert rig_line[:2] == ("◷", "0.30 → 0.60 s"), rig_line
    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.80")
    _open(page, "set_size")

    mark, value, title = _marked(page, "fix_hold")
    assert (mark, value) == ("●◷", "0.30 → 0.80 s")
    told = title.split(" · ")
    assert told[:2] == ["fix_hold", "0.30 → 0.80 s"], told
    assert "not sent · Ana (box, unverified) is changing this to 0.60" in title, title
    assert "waiting for the next trial · Ana (box, unverified)" in title, title
    assert {"draft", "waiting"} <= set(page.get_attribute(_line("fix_hold"), "class").split())

    page.click(f'{_b("fix_hold")} [data-discard]')
    assert _marked(page, "fix_hold") == rig_line


def test_a_lines_draft_text_for_each_kind(rig):
    """The plan's Global Constraints, "draft text on a line", read from the box's own fields: one
    number field, the value in force, then the typed number with its unit once ("0.30 → 0.5 s"), a
    percent's `%` ("80 → 85%"), a degree's "°", a whole number as typed ("4 → 6"); a draw, its two
    ends as typed ("0.50 s → 0.5–1.25 s"); a pool, "N of 12" from its ticks; a color and a group,
    "edited"; and a draft that cannot send, the typed text alone, marked ! as well as ●, *cannot
    send* and its reason in the title. In a real browser: run with `WLX_BROWSER=webkit` too, for
    Safari."""
    from wl_xcon.link import ParamRow

    extra = (
        ParamRow.of("distractor_fraction", "fraction", 0.0, 1.0, 0.8, False, source="task",
                    step=0.05, percent=True, section="Stimuli"),
        ParamRow.of("fix_window", "deg", 0.0, 9.0, 2.0, False, source="task", step=0.1,
                    section="Gaze windows"),
        ParamRow.of("wait", "s", 0.05, 2.0, 0.5, False, source="task", step=0.05, switch="drawn",
                    section="Timing"),
    )
    colors = tuple(row for row in _matrix_rows(40) if row.name in ("distractor_appearance", "pairings"))
    page = _task6_page(rig, params=_group_rows() + extra + colors, groups=_move_up())

    page.fill(f'{_b("fix_hold")} input[data-param="fix_hold"]', "0.5")
    page.fill(f'{_b("set_size")} input[data-param="set_size"]', "6")
    page.fill(f'{_b("distractor_fraction")} input[data-param="distractor_fraction"]', "85")
    page.fill(f'{_b("fix_window")} input[data-param="fix_window"]', "2.5")
    page.click(f'{_b("wait")} [data-switch="drawn"]')
    page.fill(f'{_b("wait")} [data-fields="non_aging"] input[data-form="shortest"]', "0.5")
    page.fill(f'{_b("wait")} [data-fields="non_aging"] input[data-form="longest"]', "1.25")
    page.click(_tick("green among red"))
    page.click(f'{_b("distractor_appearance")} .hue[data-color="red"]')
    page.fill(f'{_b("Move up")} input[data-param="move_up_bar"]', "90")
    page.fill(f'{_b("response_deadline")} input[data-param="response_deadline"]', "abc")

    for name, value in (("fix_hold", "0.30 → 0.5 s"), ("set_size", "4 → 6"),
                        ("distractor_fraction", "80 → 85%"), ("fix_window", "2.0 → 2.5°"),
                        ("wait", "0.50 s → 0.5–1.25 s"), ("pairings", "2 of 12 → 3 of 12"),
                        ("distractor_appearance", "green → edited"),
                        ("Move up", "80% · 50 → edited")):
        mark, said, title = _marked(page, name)
        assert (mark, said) == ("●", value), (name, mark, said)
        assert "not sent" in title.split(" · "), (name, title)
    mark, said, title = _marked(page, "response_deadline")
    assert (mark, said) == ("!●", "0.60 s → abc"), (mark, said)
    assert "cannot send · response_deadline needs a number" in title, title
    assert "refused" in page.get_attribute(_line("response_deadline"), "class").split()
    assert rig.dispatch.seen == []


def test_a_refusal_stays_on_its_line_while_another_is_open(rig):
    """The plan's Review Focus 5: a draft applied and refused, then another setting opened -- the
    refused one's line keeps ! and ● with its draft after the arrow, the refusal and *not sent* in
    its title, across a frame; opening it again shows the refusal on its status line and the draft
    back in its field. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.actor import Box
    from wl_xcon.link import Refused

    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.90")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    refusal = Refused("fix_hold", Box("Jake Westerberg"), "'fix_hold' at 0.9 is refused: too long",
                      cid=rig.dispatch.seen[-1].cid, value=0.9)
    _offer(rig, 41, params=_task6_rows(), refusals=(refusal,))
    _says(rig, page, "fix_hold", "refused 0.90", start=True)
    _open(page, "set_size")

    for trial in (None, 42):
        if trial is not None:
            _offer(rig, trial, params=_task6_rows(), refusals=(refusal,))
            _arrived(page, trial)
        mark, value, title = _marked(page, "fix_hold")
        assert (mark, value) == ("!●", "0.30 → 0.90 s"), (trial, mark, value)
        assert "refused 0.90 · " in title and "not sent" in title.split(" · "), title
    assert _opened(page) == ["set_size"]
    _open(page, "fix_hold")
    assert _opened(page) == ["fix_hold"]
    assert _say(page, "fix_hold").startswith("refused 0.90")
    assert page.input_value(field) == "0.90"
    assert len(rig.dispatch.seen) == 1


def test_sending_and_not_confirmed_marks(rig):
    """The plan's Global Constraints: an act sent and not yet answered by a frame marks its line …
    (*sending…* in the title), the value the one sent after the arrow; left with no word from the
    rig for `ANSWER_FRAMES` frames, the box lets it go (the whole-build review's I2) and the line
    says ? with the box's words, "not confirmed by the rig", the edit a draft again (●). In a real
    browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    page = _task6_page(rig)
    field = f'{_b("fix_hold")} input[data-param="fix_hold"]'
    page.fill(field, "0.5")
    page.evaluate("document.getElementById('sent').textContent = ''")
    page.press(field, "Enter")
    rig.wait_for(lambda: rig.dispatch.seen)
    rig.wait_for(lambda: page.text_content("#sent").strip().startswith("sent"))
    page.evaluate("document.activeElement.blur()")
    _open(page, "set_size")
    for trial in (None, 41, 42):
        if trial is not None:
            _offer(rig, trial, params=_task6_rows())
            _arrived(page, trial)
        mark, value, title = _marked(page, "fix_hold")
        assert (mark, value) == ("…", "0.30 → 0.5 s"), (trial, mark, value)
        assert "sending…" in title.split(" · "), title
    _offer(rig, 43, params=_task6_rows())
    _says(rig, page, "fix_hold", "not confirmed by the rig · check the value in force")
    mark, value, title = _marked(page, "fix_hold")
    assert (mark, value) == ("●?", "0.30 → 0.5 s"), (mark, value)
    assert "not confirmed by the rig · check the value in force" in title
    assert "unconfirmed" in page.get_attribute(_line("fix_hold"), "class").split()


def test_find_highlights_lines_and_enter_opens_the_first(rig):
    """The summary and editor design's goal 8: the find box highlights the lines it finds -- by a
    plain name, a code name, a section, a group's setting -- and dims the rest; Enter in it opens
    the first found, in the summary's order, sending nothing; cleared, nothing is highlighted or
    dimmed. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import ParamRow

    rows = tuple(dataclasses.replace(row, label="Fixation hold") if row.name == "fix_hold" else row
                 for row in _group_rows()) + (
        ParamRow.of("fix_window", "deg", 0.0, 9.0, 2.0, False, section="Gaze windows"),
        ParamRow.of("fix_size", "deg", 0.0, 9.0, 0.5, False, section="Stimuli/fixation point"),
    )
    page = _task6_page(rig, params=rows, groups=_move_up())
    every = page.locator("#params > .summary .line[data-open]").count()

    def found():
        return page.eval_on_selector_all("#params > .summary .line.found",
                                         "lines => lines.map((line) => line.getAttribute('data-open'))")

    for typed, expected in (("fixation hold", ["fix_hold"]), ("FIX_WIN", ["fix_window"]),
                            ("stimuli", ["set_size", "fix_size"]), ("move_up_window", ["Move up"])):
        page.fill("#pfind", typed)
        assert found() == expected and _found(page) == expected, typed
        assert page.locator("#params > .summary .line.nofind").count() == every - len(expected)
        assert not page.is_visible("#pfind-none"), typed
    page.fill("#pfind", "stimuli")
    page.press("#pfind", "Enter")
    assert _opened(page) == ["set_size"]
    page.fill("#pfind", "move_up_window")
    page.press("#pfind", "Enter")
    assert _opened(page) == ["Move up"]
    page.fill("#pfind", "")
    assert found() == [] and page.locator("#params > .summary .line.nofind").count() == 0
    assert rig.dispatch.seen == []


def test_find_with_no_match_opens_nothing(rig):
    """The plan's Review Focus 4: a find that matches nothing dims every line, highlights none and
    says "no setting matches"; Enter then opens nothing -- the editor keeps its placeholder, or the
    setting already opened -- and sends nothing; cleared, the words go. In a real browser: run with
    `WLX_BROWSER=webkit` too, for Safari."""
    _offer(rig, 40, params=_task6_rows())
    page = rig.browser_page()
    _sign_in(page)
    page.click('label[for="t-task"]')
    every = page.locator("#params > .summary .line[data-open]").count()
    assert every > 0
    for opened in (None, "fix_hold"):
        if opened is not None:
            page.fill("#pfind", "")
            _open(page, opened)
        page.fill("#pfind", "no such setting")
        assert page.locator("#params > .summary .line.nofind").count() == every
        assert page.locator("#params > .summary .line.found").count() == 0
        assert page.is_visible("#pfind-none")
        assert page.text_content("#pfind-none") == "no setting matches"
        page.press("#pfind", "Enter")
        # The opened setting stays opened, the editor saying find hides it (the ledger's ruling
        # for the build's Task 3: `test_the_editor_says_when_find_hides_the_opened_setting`).
        assert _opened(page) == (["click a setting above to change it"] if opened is None
                                 else [web.FIND_HIDES_OPENED, opened])
    page.fill("#pfind", "")
    assert not page.is_visible("#pfind-none")
    assert rig.dispatch.seen == []


def test_the_editor_says_when_find_hides_the_opened_setting(rig):
    """The ledger's ruling for the summary and editor build's Task 3: where the find box hides the
    setting opened in the editor, the editor says "the opened setting is hidden by find · clear
    find to see it" in place of going blank (Task 2's concern 3) -- across a frame, and on the
    Training tab as on Task parameters; a find that finds it, or none, takes the words away and
    shows its box again, still opened. In a real browser: run with `WLX_BROWSER=webkit` too, for
    Safari."""
    rows = _task6_rows() + _training_rows(2.0)
    page = _task6_page(rig, params=rows)
    note = "#params > .editing > .findhid"
    assert page.is_hidden(note), "no find, no words"
    _open(page, "fix_hold")
    page.fill("#pfind", "set_size")
    assert page.is_visible(note) and page.text_content(note) == web.FIND_HIDES_OPENED
    assert page._page.is_hidden(_b("fix_hold")) and page.is_hidden("#params > .editing > .placeholder")
    assert _opened(page) == [web.FIND_HIDES_OPENED, "fix_hold"]
    _offer(rig, 41, params=rows)
    _arrived(page, 41)
    assert page.is_visible(note), "a frame keeps the words"
    page.fill("#pfind", "fix")
    assert page.is_hidden(note) and page._page.is_visible(_b("fix_hold"))
    page.fill("#pfind", "set_size")
    page.fill("#pfind", "")
    assert page.is_hidden(note) and _opened(page) == ["fix_hold"]

    page.click('label[for="t-training"]')
    _open(page, "fade_in_step", "#training-params")
    page.fill("#tfind", "gain")
    assert page.is_visible("#training-params > .editing > .findhid")
    assert page.is_hidden(note), "each tab's own find"


def test_the_training_tab_is_a_summary_below_the_switch_and_ladder(rig, tmp_path):
    """The summary and editor design's call on the Training tab: "the training switch and the stage
    ladder stay where they are; the summary and the editor replace the boxes in its settings
    panel, below them". On the pop-out's own Training settings (`_popout_own`): the switch and the
    trainer's panel stand above the summary; each of the three rules is one line (the group's
    title, its settings' values), none of their settings a line of its own, and each opens as its
    sentence with its fields in place; its find works as Task parameters' does; its columns are as
    wide as its own longest line (the ledger's ruling for the build's Task 3), no name cut. Through
    the wire, in a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_own(tmp_path, **_TRAINING, shaping="on", full_task=True))))
    page = rig.browser_page()
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    page.click('label[for="t-training"]')
    page.wait_for_selector("#training-params > .summary .line", state="visible")
    top = page.evaluate("document.querySelector('#training-params > .summary').getBoundingClientRect().top")
    for above in ("#shaping", "#rt-train"):
        assert page.is_visible(above), above
        bottom = page.evaluate(f"document.querySelector('{above}').getBoundingClientRect().bottom")
        assert bottom <= top, (above, bottom, top)
    assert page.locator("#shaping [data-cmd=shaping]").count() == 3, "the switch"

    lines = dict(page.eval_on_selector_all("#training-params > .summary .line[data-open]", """all =>
        all.map((line) => [line.getAttribute('data-open'), [line.querySelector('.ln').textContent,
        line.querySelector('.lv').textContent, line.getBoundingClientRect().height]])"""))
    sentences = {"Move up": "Move up when at least ", "Move back": "Move back when fewer than ",
                 "Staircase": "One level harder after "}
    for rule, starts in sentences.items():
        label, value, height = lines[rule]
        assert label == rule and 18 <= height <= 22, (rule, lines[rule])
        assert " · " in value, (rule, value, "its settings' values")
        page._page.click(_line(rule, "#training-params"))
        assert _opened(page, "#training-params") == [rule]
        said = page.text_content(f'{_b(rule, "#training-params")} .editor .sentence > .gs')
        assert said == starts, (rule, said)
    members = {"move_up_bar", "move_up_window", "move_back_bar", "move_back_window",
               "staircase_down", "staircase_up"}
    assert not members & set(lines), "a rule's settings are its one line"

    page.fill("#tfind", "staircase")
    assert "Staircase" in _found(page, "#training-params")
    page.fill("#tfind", "")
    width = page.get_attribute("#training-params > .summary", "style")
    assert width is not None and re.fullmatch(r"column-width: [0-9.]+ch", width), width
    assert page.get_attribute("#params > .summary", "style") != width, "each tab its own"
    cut = page.eval_on_selector_all("#training-params > .summary .line > .ln, "
                                    "#training-params > .summary .line > .lv", """parts =>
        parts.filter((part) => part.scrollWidth > part.clientWidth + 0.5).map((part) =>
        part.textContent)""")
    assert cut == [], cut


def test_the_real_popout_summary_has_three_columns_or_more_at_1280(rig, tmp_path):
    """The ledger's ruling for the summary and editor build's Task 3: "size the summary's columns
    from the tab's own longest line ... so the real pop-out gets 3-4 columns at 1280 while a
    40-character label still fits uncut" (`test_no_popout_name_is_cut_at_1280`, beside it). On the
    wl-xtasks pop-out's own rows at their start values, at 1280 × 800 with the demo screen's
    column shown: three columns or more on Task parameters and on Training, no name and no value
    cut, every Task parameters line above the fold; and at 1024 and 1440 nothing cut. Through the
    wire, in a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    from wl_xcon.link import decode, encode

    rig.hub.offer(decode(encode(_popout_own(tmp_path, demo=True))))
    page = rig.browser_page()
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    page.click('label[for="t-task"]')
    page.wait_for_selector("#params > .summary .line", state="visible")
    assert page.is_visible("#demo-pane"), "the demo screen's column is shown"
    columns = """(root) => new Set(Array.from(document.querySelectorAll(root + ' > .summary .line'))
        .filter((line) => line.getClientRects().length).map((line) =>
        Math.round(line.getBoundingClientRect().left))).size"""
    cuts = """(root) => Array.from(document.querySelectorAll(root + ' > .summary .line > .ln, ' + root +
        ' > .summary .line > .lv')).filter((part) => part.getClientRects().length &&
        part.scrollWidth > part.clientWidth + 0.5).map((part) => part.textContent)"""
    assert page.evaluate(columns, "#params") >= 3
    below = page.eval_on_selector_all("#params > .summary .line", """lines => lines.filter(
        (line) => line.getBoundingClientRect().bottom + window.scrollY > 800).map(
        (line) => line.getAttribute('data-open'))""")
    assert below == [], below
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": LAPTOP_H})
        assert page.evaluate(cuts, "#params") == [], width
    page.set_viewport_size({"width": 1280, "height": LAPTOP_H})
    page.click('label[for="t-training"]')
    page.wait_for_selector("#training-params > .summary .line", state="visible")
    # Its eight lines are fewer than three columns' worth, so the engine balances them into what
    # it needs (WebKit two): its columns' width leaves room for three.
    room = page.evaluate("""() => { const summary = document.querySelector('#training-params > .summary');
        const style = getComputedStyle(summary);
        return [parseFloat(style.columnWidth), parseFloat(style.columnGap), summary.clientWidth]; }""")
    assert 3 * room[0] + 2 * room[1] <= room[2], room
    assert page.evaluate(columns, "#training-params") >= 2, "its one section breaks between its subsections"
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": LAPTOP_H})
        assert page.evaluate(cuts, "#training-params") == [], width


def test_a_frame_that_lengthens_a_name_widens_its_columns_in_place(rig):
    """The ledger's ruling for the summary and editor build's Task 3, across frames: a frame whose
    longest line is longer -- a plain name the rig now gives -- widens the summary's columns, the
    summary and its lines patched in place (the nodes kept, a focused line keeping its focus), and
    one that shortens it again narrows them. In a real browser: run with `WLX_BROWSER=webkit` too,
    for Safari."""
    page = _task6_page(rig)
    narrow = page.get_attribute("#params > .summary", "style")
    page.evaluate("document.querySelector('#params > .summary').wlxKept = 1")
    page._page.focus(_line("set_size"))
    long = _task6_rows(fix_hold={"label": "Fixation hold, before the array is shown"})
    _offer(rig, 41, params=long)
    _arrived(page, 41)
    _until(page, "document.querySelector('#params > .summary').getAttribute('style') !== " + json.dumps(narrow))
    wide = page.get_attribute("#params > .summary", "style")
    assert float(wide.split()[-1][:-2]) > float(narrow.split()[-1][:-2]), (narrow, wide)
    assert page.evaluate("document.querySelector('#params > .summary').wlxKept === 1"), "patched in place"
    assert page.evaluate(f"document.activeElement === document.querySelector('{_line('set_size')}')")
    _offer(rig, 42, params=_task6_rows())
    _arrived(page, 42)
    _until(page, "document.querySelector('#params > .summary').getAttribute('style') === " + json.dumps(narrow))


def test_the_summary_steps_with_the_arrow_keys(rig):
    """The summary and editor design's goal 7: on a summary line, ↓ and ↑ move to the next and the
    previous line in the summary's order, past the lines the find box dims, and stop at the ends;
    Enter opens the setting and puts its editor's first field in focus; Esc in that field, with no
    draft, leaves it, and a second Esc returns focus to its line (the design's call). Nothing is
    sent. In a real browser: run with `WLX_BROWSER=webkit` too, for Safari."""
    page = _task6_page(rig)
    order = page.eval_on_selector_all("#params > .summary .line[data-open]",
                                      "lines => lines.map((line) => line.getAttribute('data-open'))")
    assert order[:3] == ["fix_hold", "response_deadline", "set_size"], order

    def focused():
        return page.evaluate("document.activeElement.getAttribute('data-open') || "
                             "document.activeElement.getAttribute('data-param') || "
                             "document.activeElement.tagName")

    page.focus(_line("fix_hold"))
    for key, expected in (("ArrowDown", "response_deadline"), ("ArrowDown", "set_size"),
                          ("ArrowUp", "response_deadline"), ("ArrowUp", "fix_hold"),
                          ("ArrowUp", "fix_hold")):
        page.keyboard.press(key)
        assert focused() == expected, (key, expected)
    page.focus(_line(order[-1]))
    page.keyboard.press("ArrowDown")
    assert focused() == order[-1]
    page.fill("#pfind", "set_size")
    page.focus(_line("fix_hold"))
    page.keyboard.press("ArrowDown")
    assert focused() == "set_size", "past the lines the find box dims"
    page.fill("#pfind", "")

    page.focus(_line("response_deadline"))
    page.keyboard.press("Enter")
    assert _opened(page) == ["response_deadline"]
    assert focused() == "response_deadline" and page.evaluate(
        "document.activeElement.tagName") == "INPUT", "the editor's first field"
    page.keyboard.press("Escape")
    assert focused() == "BODY", "Esc with no draft leaves the field"
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.matches('.summary .line[data-open=\"response_deadline\"]')")
    assert rig.dispatch.seen == []


def test_a_frame_during_a_press_on_a_line_opens_it_once(rig):
    """The plan's Review Focus 1: a frame lands while a summary line is pressed -- one changing that
    line's value and its neighbors' -- and the press opens the setting once, the line's node kept
    and its value the frame's after; then, a field of the opened box being typed in, another frame
    changes the setting's value in force: the field keeps its focus and its draft, and the line
    says the draft over the new value in force. In a real browser: run with `WLX_BROWSER=webkit`
    too, for Safari."""
    page = _task6_page(rig, params=_matrix_rows(40))
    line = _line("set_size")
    page.evaluate("""(line) => {
        window.__opens = 0;
        document.querySelector(line).wlxSame = true;
        document.addEventListener('click', (e) => {
            if (e.target.closest && e.target.closest(line)) { window.__opens += 1; } }, true);
    }""", line)
    page.hover(line)
    page.mouse.down()
    _offer(rig, 41, params=_matrix_rows(41))
    _arrived(page, 41)
    assert page.text_content(f"{line} > .lv") == "4", "held while the line is pressed"
    page.mouse.up()
    rig.wait_for(lambda: page.text_content(f"{line} > .lv") == "6")
    assert _opened(page) == ["set_size"]
    assert page.evaluate("window.__opens") == 1
    assert page.evaluate("(line) => document.querySelector(line).wlxSame === true", line)

    field = f'{_b("set_size")} input[data-param="set_size"]'
    page.fill(field, "8")
    rows = tuple(dataclasses.replace(row, value=7) if row.name == "set_size" else row
                 for row in _matrix_rows(41))
    _offer(rig, 42, params=rows)
    _arrived(page, 42)
    rig.wait_for(lambda: page.text_content(f"{line} > .lv") == "7 → 8")
    assert page.evaluate("document.activeElement.getAttribute('data-param')") == "set_size"
    assert page.input_value(field) == "8" and _marked(page, "set_size")[0] == "●"
    assert page.evaluate("(line) => document.querySelector(line).wlxSame === true", line)
    assert rig.dispatch.seen == []
