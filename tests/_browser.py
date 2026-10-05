"""A real browser, and a fake wl.works served over https, for the page's script (b2b spec
§8; closes XC-186). Imported by `test_page_browser.py`; never collected.

`chromium()` skips when Playwright or its Chromium is missing, and fails instead under
`WLX_REQUIRE_BROWSER=1`, so CI cannot pass by skipping. `FakeWlWorks` answers the two
endpoints the page uses, with the checks wl.works' own would make (`rig-sign-in.ts`,
`rig-cors.ts`), and never writes a token anywhere: it keeps only counters, the renewal
tokens it was shown (to count reuse), and the sentence of each refusal.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

REQUIRED = os.environ.get("WLX_REQUIRE_BROWSER") == "1"
INSTALL = "python -m playwright install chromium"

#: wl-works `rig-sign-in.ts`'s words for a renewal it will not give.
OLD_SIGN_IN = "This sign-in at the rig is 24 hours old. Sign in again at the rig."


def _unavailable(why: str):
    if REQUIRED:
        raise AssertionError(f"WLX_REQUIRE_BROWSER=1 but no browser: {why}")
    pytest.skip(why)


@contextmanager
def chromium():
    """A Playwright `Browser`, closed (and Playwright stopped) on the way out."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        _unavailable(f"playwright is not installed ({exc}); pip install -e '.[browser]', then {INSTALL}")
    playwright = sync_playwright().start()
    try:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Playwright's own error type is not stable
            _unavailable(f"Chromium would not launch ({type(exc).__name__}); run {INSTALL}")
        try:
            yield browser
        finally:
            browser.close()
    finally:
        playwright.stop()


class FakeWlWorks:
    """wl.works' authorize and token endpoints, over https, for one rig page."""

    def __init__(self, issuer, page: str, origin: str, tls: dict, port: int) -> None:
        from wl_xcon.serve import _PageServer, tls_context

        self.issuer = issuer
        self.page = page
        self.origin = origin
        self.client = "wl-works-rig-rig-3"
        self.expires_in = 3600
        #: When set, the `expires_in` the answer *says*, while the token's own `exp` stays
        #: `expires_in`: a token that lapses at the rig sooner than the page was told.
        self.told_expires_in: int | None = None
        #: Set by a test: every renewal is then refused, in wl.works' words.
        self.refuse_renewal = False
        #: Seconds a renewal's answer is held back (housekeeping), and an event it also waits on.
        self.renewal_delay = 0.0
        self.renewal_gate: threading.Event | None = None
        self.renewals = 0
        self.exchanges = 0
        #: Why each refused authorize request was refused. Never a token.
        self.refused: list[str] = []
        #: Every renewal token shown to the token endpoint, in order.
        self.presented: list[str] = []
        #: Every authorization code issued, for a test that looks for one in a log.
        self.codes: list[str] = []
        self._pending: dict[str, str] = {}
        self._live: set[str] = set()
        self._spent: set[str] = set()
        self._serial = 0
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:  # a code rides in a query: log nothing
                pass

            def _send(self, status: int, body: dict | None = None, extra=()) -> None:
                raw = json.dumps(body).encode("utf-8") if body is not None else b""
                self.send_response(status)
                for name, value in extra:
                    self.send_header(name, value)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _cors(self):
                return (("Access-Control-Allow-Origin", fake.origin), ("Vary", "Origin"))

            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                if parts.path != "/api/auth/oauth2/authorize":
                    self._send(404, {"error": "not_found"})
                    return
                query = {key: values[0] for key, values in parse_qs(parts.query, keep_blank_values=True).items()}
                why = fake._authorize_problem(query, "prompt" in query)
                if why:
                    fake.refused.append(why)
                    self._send(400, {"error": "invalid_request", "error_description": why})
                    return
                code = secrets.token_urlsafe(16)
                with fake._lock:
                    fake._pending[code] = query["code_challenge"]
                    fake.codes.append(code)
                back = fake.page + "?" + urlencode({"code": code, "state": query["state"]})
                self._send(302, None, (("Location", back),))

            def do_OPTIONS(self) -> None:
                if urlsplit(self.path).path != "/api/auth/oauth2/token":
                    self._send(404, {"error": "not_found"})
                    return
                self._send(204, None, self._cors() + (
                    ("Access-Control-Allow-Methods", "POST, OPTIONS"),
                    ("Access-Control-Allow-Headers", "Content-Type"),
                    ("Access-Control-Max-Age", "600"),
                ))

            def do_POST(self) -> None:
                if urlsplit(self.path).path != "/api/auth/oauth2/token":
                    self._send(404, {"error": "not_found"})
                    return
                length = int(self.headers.get("Content-Length") or 0)
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8")).items()}
                status, body = fake._token(form)
                self._send(status, body, self._cors() + (("Cache-Control", "no-store"),))

        self.server = _PageServer(("127.0.0.1", port), Handler, tls_context(tls["cert"], tls["key"]))
        self._thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if self.renewal_gate is not None:
            self.renewal_gate.set()  # a handler held by a test that failed must end
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)

    def _authorize_problem(self, query: dict, has_prompt: bool) -> str:
        wanted = {
            "client_id": self.client, "redirect_uri": self.page, "scope": "offline_access",
            "resource": self.origin, "code_challenge_method": "S256", "response_type": "code",
        }
        for name, value in wanted.items():
            if query.get(name) != value:
                return f"authorize: {name} is not what wl.works registered"
        if has_prompt:
            return "authorize: the page must not send prompt"
        if not query.get("code_challenge") or not query.get("state"):
            return "authorize: a challenge and a state are needed"
        return ""

    def _grant(self) -> dict:
        with self._lock:
            self._serial += 1
            refresh = f"r-{self._serial}"
            self._live.add(refresh)
        return {
            "access_token": self.issuer.mint(aud=self.origin, exp_in=self.expires_in),
            "refresh_token": refresh,
            "expires_in": self.expires_in if self.told_expires_in is None else self.told_expires_in,
            "token_type": "Bearer",
        }

    def _token(self, form: dict) -> tuple[int, dict]:
        grant = form.get("grant_type")
        if grant == "authorization_code":
            with self._lock:
                challenge = self._pending.pop(form.get("code", ""), None)
            verifier = form.get("code_verifier", "")
            digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
            if (
                challenge is None or digest != challenge
                or form.get("client_id") != self.client or form.get("redirect_uri") != self.page
            ):
                return 400, {"error": "invalid_grant", "error_description": "the code does not check out"}
            with self._lock:
                self.exchanges += 1
            return 200, self._grant()
        if grant == "refresh_token":
            presented = form.get("refresh_token", "")
            with self._lock:
                self.renewals += 1
                self.presented.append(presented)
            if self.renewal_delay:
                threading.Event().wait(self.renewal_delay)
            if self.renewal_gate is not None:
                self.renewal_gate.wait(timeout=20.0)  # bounded: a test that fails must not hang
            if self.refuse_renewal or form.get("client_id") != self.client:
                return 400, {"error": "invalid_grant", "error_description": OLD_SIGN_IN}
            with self._lock:
                # better-auth 1.7.1 with a reuse interval of 0: a second presentation of a
                # token is a reuse.
                if presented not in self._live or presented in self._spent:
                    return 400, {"error": "invalid_grant", "error_description": "this renewal token was used already"}
                self._spent.add(presented)
            return 200, self._grant()
        return 400, {"error": "unsupported_grant_type"}
