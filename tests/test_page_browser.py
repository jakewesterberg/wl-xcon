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
from dataclasses import replace

import pytest

pytest.importorskip("jwt")

from _browser import REQUIRED, FakeWlWorks, chromium  # noqa: E402
from _frames import ENDPOINT, frame  # noqa: E402
from _issuer import Issuer  # noqa: E402
from _ports import endpoints as free_endpoints  # noqa: E402
from _tls import client_context, material  # noqa: E402
from wl_xcon import signin  # noqa: E402
from wl_xcon.link import ManualReward, Pause  # noqa: E402
from wl_xcon.serve import Hub, Remote, _PageServer, make_handler, tls_context  # noqa: E402

_ = REQUIRED  # imported so a missing browser's failure mode is read from one place
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
        self._pages: list = []
        tls = material(tmp_path)
        self.tls = tls
        self.context = client_context(tls["ca"])
        rig_port, fake_port = (int(item.rsplit(":", 1)[1]) for item in free_endpoints(2))
        self.port = rig_port
        self.page_url = f"https://127.0.0.1:{rig_port}/"
        self.origin = f"https://127.0.0.1:{rig_port}"
        self.issuer = Issuer(issuer=f"https://127.0.0.1:{fake_port}/api/auth")
        self.fake = FakeWlWorks(self.issuer, self.page_url, self.origin, tls, fake_port)
        self.dispatch = _Dispatch()
        self.hub = Hub(steady=_Clock(), endpoint=ENDPOINT)
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
        self._thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)

    def start(self) -> None:
        self.fake.start()
        self._thread.start()

    def browser_page(self):
        """A Playwright page, in a context of its own, already at the rig's page."""
        context = self._browser.new_context(ignore_https_errors=True)
        self._contexts.append(context)
        page = context.new_page()
        page.set_default_timeout(WAIT_S * 1000)
        self._pages.append(page)
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
        for page in self._pages:
            try:
                page.unroute_all(behavior="ignoreErrors")
            except Exception:  # noqa: BLE001
                pass
        for context in self._contexts:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
        if self.dispatch.gate is not None:
            self.dispatch.gate.set()
        self.hub.close()
        try:
            self.server.shutdown()
            self.server.server_close()
        finally:
            self._thread.join(timeout=5)
            self.fake.stop()


@pytest.fixture
def rig(tmp_path):
    with chromium() as browser:
        made = _Rig(tmp_path, browser)
        made.start()
        try:
            yield made
        finally:
            made.close()


def _stored(page) -> dict | None:
    return page.evaluate("JSON.parse(window.sessionStorage.getItem('wlx-signin') || 'null')")


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


def _pauses(rig) -> list:
    return [seen for seen in rig.dispatch.seen if isinstance(seen, Pause)]


def _rewards(rig) -> list:
    return [seen for seen in rig.dispatch.seen if isinstance(seen, ManualReward)]


def test_a_member_signs_in_and_a_pause_reaches_the_rig_as_theirs(rig):
    page = rig.browser_page()
    page.click("#signin")
    page.wait_for_selector(SIGNED_IN, timeout=10_000)
    assert "code=" not in page.url
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
    assert rig.fake.exchanges == 0
    assert page.inner_text("#member") == ""
    assert _stored(page) is None


def test_a_short_token_is_renewed_before_a_command(rig):
    rig.fake.expires_in = 4  # housekeeping: short enough that a renewal is due at once
    page = rig.browser_page()
    _sign_in(page)
    time.sleep(3)  # housekeeping
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    assert rig.fake.renewals >= 1
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)"


def test_a_refused_renewal_signs_the_page_out_with_wl_works_sentence(rig):
    rig.fake.expires_in = 4
    page = rig.browser_page()
    _sign_in(page)
    rig.fake.refuse_renewal = True
    page.wait_for_selector("#sent:has-text('24 hours old')")
    assert page.is_disabled(PAUSE)
    assert page.inner_text("#member") == ""
    assert _stored(page) is None


def test_sign_out_makes_the_rig_refuse_the_old_token(rig):
    page = rig.browser_page()
    _sign_in(page)
    access = _stored(page)["access"]
    page.click("#signout")
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
    assert _rewards(rig) == []
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
    leaked = [code for code in rig.fake.codes if code in logged] + [t for t in (access, refresh) if t in logged]
    assert leaked == []


def test_overlapping_renewal_triggers_present_one_renewal_token(rig):
    rig.fake.expires_in = 4  # housekeeping: a renewal is due as soon as the page is signed in
    rig.fake.renewal_delay = 0.6  # housekeeping: long enough that the two triggers overlap
    page = rig.browser_page()
    _sign_in(page)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    page.click(PAUSE)
    rig.wait_for(lambda: _pauses(rig))
    presented = list(rig.fake.presented)
    assert len(presented) >= 1
    assert len(set(presented)) == len(presented)
    assert page.inner_text("#member") == "Jake Westerberg (wl.works)"
    assert _stored(page) is not None


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
    rig.wait_for(lambda: page.inner_text("#sent") != "sending…")
    assert len(_rewards(rig)) == 1


def test_a_reload_with_a_lapsed_token_renews_and_stays_signed_in(rig, monkeypatch):
    # The rig allows a minute past a token's end (`signin.LEEWAY_S`); none here, so a few
    # seconds is a lapse. The page is told the token lasts an hour, as a page whose
    # token ran out sooner than said would be: it asks the rig, which says `expired`.
    monkeypatch.setattr(signin, "LEEWAY_S", 0)
    rig.fake.expires_in = 3
    rig.fake.told_expires_in = 3600
    page = rig.browser_page()
    _sign_in(page)
    time.sleep(4)  # housekeeping: past the token's own end
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
    time.sleep(0.5)  # housekeeping: the late answer has arrived by now

    def signed_out() -> bool:
        return page.inner_text("#member") == "" and page.is_disabled(PAUSE) and _stored(page) is None

    assert signed_out()
    time.sleep(1.5)
    assert signed_out()
