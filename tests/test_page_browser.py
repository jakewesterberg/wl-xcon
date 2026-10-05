"""The rig's https page, driven in a real browser (b2b spec §8; closes XC-186).

The page's script was tested by reading its text, which let two of b3a-2's defects
through. These tests run it: Chromium signs in against a fake wl.works served over https
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

from _browser import REQUIRED, FakeWlWorks, chromium  # noqa: E402

try:
    import jwt  # noqa: F401
except ImportError:
    if REQUIRED:
        raise
    pytest.skip("PyJWT is not installed (the signin extra)", allow_module_level=True)

from _frames import ENDPOINT, frame  # noqa: E402
from _issuer import Issuer  # noqa: E402
from _ports import endpoints as free_endpoints  # noqa: E402
from _tls import client_context, material  # noqa: E402
from wl_xcon import signin  # noqa: E402
from wl_xcon.link import ManualReward, Pause  # noqa: E402
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
    def __init__(self, tmp_path, browser) -> None:
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
    with chromium() as browser:
        made = _Rig(tmp_path, browser)  # closes what it opened itself if it fails
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
    _sign_in(page)
    rig.fake.stop()  # wl.works goes down, and stays down
    # The renewal fails with time left: the sign-in stands, and the page will try again.
    page.wait_for_selector("#sent:has-text('trying again before it lapses')")
    assert page.evaluate("document.body.getAttribute('data-signed-in')") == "1"
    assert _has_signin(page)
    # At the token's end, with no press, the page signs itself out and says why.
    _until(page, "document.body.getAttribute('data-signed-in') === '0'", rig.fake.expires_in + WAIT_S)
    assert _signed_out_by_the_page(page)
    assert page.inner_text("#sent") == "signed out: " + UNREACHED
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
    checks.clear()  # the rig holds every check from here
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    # wl.works has renewed, and the rig has not yet confirmed the new token. A bool: never a token.
    _until(page, "JSON.parse(window.sessionStorage.getItem('wlx-signin')).access !== window.__first")
    page.click(PAUSE)
    _until(page, "window.__clicks >= 1")  # the click's handler has run
    told = page.inner_text("#sent")
    assert not told.startswith("not sent")  # the press waits for the renewal, refused by nothing
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
    page.wait_for_selector("#sent:has-text('trying again before it lapses')")
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
    page.wait_for_selector(SIGNED_IN)
    assert rig.fake.renewals >= 1
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
