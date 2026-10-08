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

import json
import threading
import time

import pytest

from _browser import REQUIRED, FakeWlWorks, browser  # noqa: E402

try:
    import jwt  # noqa: F401
except ImportError:
    if REQUIRED:
        raise
    pytest.skip("PyJWT is not installed (the signin extra)", allow_module_level=True)

from _frames import ENDPOINT, frame, idle  # noqa: E402
from _issuer import Issuer  # noqa: E402
from _ports import endpoints as free_endpoints  # noqa: E402
from _tls import client_context, material  # noqa: E402
from wl_xcon import signin, web  # noqa: E402
from wl_xcon.findings import SESSION_KINDS  # noqa: E402
from wl_xcon.link import ManualReward, OpenSession, Pause, WarningRow  # noqa: E402
from wl_xcon.warnlist import HEAD_FREE  # noqa: E402
from wl_xcon.serve import Hub, Remote, _PageServer, make_handler, tls_context  # noqa: E402

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

    def __call__(self, request):
        self.seen.append(request)
        if isinstance(request, ManualReward) and self.gate is not None:
            self.entered.set()
            self.gate.wait(timeout=20.0)  # bounded: a failing test must not hang its teardown
        return 200, {"status": "sent", "said": "sent: test"}


class _Rig:
    def __init__(self, tmp_path, browser, *, keys: bool = True) -> None:
        self._browser = browser
        self._contexts: list = []
        self._thread = None
        self.fake = None
        self.dispatch = _Dispatch()
        self.hub = Hub(steady=_Clock(), endpoint=ENDPOINT)
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
                    remote=Remote(rig_page, self.checker),
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
        page = context.new_page()
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
    second = first.context.new_page()  # a tab of the same browser
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
    second = first.context.new_page()
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
    second = first.context.new_page()
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
    assert len(loads) == 1
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
    the member."""
    page = rig.browser_page()
    _sign_in(page)
    rig.hub.offer(idle())
    page.wait_for_selector('#dn-warnings [data-warn="default calibration"]', state="attached")
    page.click('[data-cmd="new"]')
    page.select_option("#dn-subject", "A")
    page.select_option("#dn-kind", "training")
    page.fill("#dn-id", "s-1")
    page.fill("#dn-left", "07:30")
    page.check("#dn-accept")
    page.click("#dn-ok")
    rig.wait_for(lambda: any(isinstance(seen, OpenSession) for seen in rig.dispatch.seen))
    opened = next(seen for seen in rig.dispatch.seen if isinstance(seen, OpenSession))
    assert opened.session_kind == "training"
    assert opened.by.name == "Jake Westerberg"
    assert [pair[0] for pair in opened.accepted] == ["default calibration"]
    assert opened.accepted[0][1] == "the sRGB standard's"


def _opens(rig) -> list:
    return [seen for seen in rig.dispatch.seen if isinstance(seen, OpenSession)]


def _fill_open(page) -> None:
    page.click('[data-cmd="new"]')
    page.select_option("#dn-subject", "A")
    page.select_option("#dn-kind", "training")
    page.fill("#dn-id", "s-1")
    page.fill("#dn-left", "07:30")


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
