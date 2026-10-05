"""Checking a wl.works sign-in at a rig's page (P4d-2b b2b).

Spec: `docs/superpowers/specs/2026-10-02-p4d2b-b2b-remote-signin-design.md` §3-§5,
against wl-works' rig sign-in as built and deployed on 2026-10-02 (`4eb2c568`; its
`src/lib/rigs.ts`, `src/lib/rig-sign-in.ts` and `src/lib/rig-cors.ts`, and
`createJwtAccessToken` in `@better-auth/oauth-provider` 1.7.1, read that day).

**Used only by `wlx serve`, and only when `--https` is given**, which is the only time
`jwt` and `cryptography` (the `signin` extra) are imported
(`tests/test_no_transport_leak.py` proves `serve` imports without them).

**Offline by design** (the PI, 2026-09-27): a token is checked against wl.works'
published keys, cached here, never by asking wl.works about it. So a token already
issued keeps working through a wl.works outage, and through a sign-out at wl.works,
until its hour ends; a sign-out at this page is refused here at once (`sign_out`).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import ssl
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import jwt

from wl_xcon import actor as actors

#: wl.works' client id for a rig is this and the rig's name (`RIG_CLIENT_PREFIX`,
#: wl-works `src/lib/rigs.ts`, read 2026-10-02).
CLIENT_PREFIX = "wl-works-rig-"
#: A rig's name, as wl.works' `parseRigPages` allows it.
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
NAME_MAX = 32
#: Housekeeping, not measurements (spec §5): the outbound fetch's timeout, the largest
#: document read, and how often an unknown key id may fetch the key set again, and a
#: rig with no keys retries.
FETCH_TIMEOUT_S = 5.0
FETCH_LIMIT = 65536
REFETCH_EVERY_S = 60.0
RETRY_EVERY_S = 60.0
#: The refusal a rig with no keys gives a command from the network (spec §5).
NO_KEYS = "the rig has not reached wl.works to check sign-ins; use the rig PC"


@dataclass(frozen=True, slots=True)
class RigPage:
    """This rig's entry in wl.works' `RIG_PAGES`: its name, its page's address exactly
    as configured (the one return address wl.works compares as a string), the page's
    origin (the token's audience), wl.works' client id for it, and the `Host` a
    browser sends for it."""

    name: str
    page: str
    origin: str
    client_id: str
    host: str


def parse_rig_page(text: str) -> RigPage:
    """`--rig-page NAME=URL`, by wl.works' own `parseRigPages` rules, so a page wl.works
    would refuse to configure is refused here too. Raises `ValueError` with a sentence."""
    name, eq, page = text.partition("=")
    shape = f'--rig-page takes NAME=URL, as wl.works\' RIG_PAGES does, such as "rig-3=https://rig-3.wl.works/"'
    if not eq:
        raise ValueError(f'{shape}; {text!r} has no "="')
    if not _NAME.fullmatch(name) or len(name) > NAME_MAX:
        raise ValueError(
            f"{shape}; its name is lower-case letters and digits, joined by single hyphens, "
            f"at most {NAME_MAX} long"
        )
    if "," in page:
        raise ValueError(f"{shape}; its address has a comma, which wl.works refuses")
    parts = urlsplit(page)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(f"{shape}; its address must be an absolute https address")
    if parts.username is not None or parts.password is not None:
        raise ValueError(f"{shape}; its address carries a user name or password")
    if parts.fragment or "#" in page:
        raise ValueError(f"{shape}; its address has a fragment (#)")
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    netloc = host if port in (None, 443) else f"{host}:{port}"
    return RigPage(name, page, f"https://{netloc}", CLIENT_PREFIX + name, netloc)


@dataclass(frozen=True, slots=True)
class Discovery:
    """What this rig reads from wl.works' discovery document (spec §5)."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str

    @property
    def token_origin(self) -> str:
        """The token endpoint's origin: the one outside address the page may `fetch`."""
        parts = urlsplit(self.token_endpoint)
        return f"{parts.scheme}://{parts.netloc}"


def _discovery(data: object, issuer: str) -> Discovery:
    """The document's four fields, checked. **Its issuer must be the configured one,
    exactly** (OpenID Connect Discovery 1.0 §4.3). Raises `ValueError`."""
    if not isinstance(data, dict) or data.get("issuer") != issuer:
        raise ValueError(f"wl.works' discovery document does not name the issuer {issuer!r}")
    fields = ("authorization_endpoint", "token_endpoint", "jwks_uri")
    for field in fields:
        value = data.get(field)
        if not isinstance(value, str) or urlsplit(value).scheme != "https":
            raise ValueError(f"wl.works' discovery document's {field} is not an https address")
    return Discovery(issuer, *(data[field] for field in fields))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A discovery document or key set that redirects is refused, never followed: a
    redirect could leave https."""

    def redirect_request(self, *args, **kwargs):
        return None


def fetch_json(url: str, *, context: ssl.SSLContext | None = None) -> dict:
    """GET one JSON object over https, with the system's certificate checks (or
    `context`'s, in a test), no redirects, `FETCH_TIMEOUT_S` and at most `FETCH_LIMIT`
    bytes. Raises `ValueError`, `OSError` or `http.client.HTTPException`."""
    if urlsplit(url).scheme != "https":
        raise ValueError(f"{url!r} is not an https address")
    opener = urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=context or ssl.create_default_context())
    )
    with opener.open(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=FETCH_TIMEOUT_S) as response:
        if response.status != 200:
            raise ValueError(f"{url!r} answered {response.status}")
        body = response.read(FETCH_LIMIT + 1)
    if len(body) > FETCH_LIMIT:
        raise ValueError(f"{url!r} answered more than {FETCH_LIMIT} bytes")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError(f"{url!r} did not answer a JSON object")
    return data


def _keys(jwks: object) -> dict:
    """Key id → RSA public key, for every key a rig token can be signed with: RSA, its
    `use` absent or `sig`, its `alg` absent or RS256. Anything else is ignored."""
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise ValueError("wl.works' key set holds no list of keys")
    keys = {}
    for jwk in jwks["keys"]:
        if not isinstance(jwk, dict) or jwk.get("kty") != "RSA":
            continue
        if jwk.get("use") not in (None, "sig") or jwk.get("alg") not in (None, "RS256"):
            continue
        kid = jwk.get("kid")
        if not isinstance(kid, str) or not kid:
            continue
        try:
            keys[kid] = jwt.PyJWK(jwk, algorithm="RS256").key
        except (jwt.exceptions.PyJWTError, ValueError, TypeError):
            continue
    return keys


def _save(path: Path, discovery: dict, jwks: dict) -> None:
    """Both documents to `path`, replaced whole, so a crash mid-write leaves the old one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump({"discovery": discovery, "jwks": jwks}, out)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class Checker:
    """This rig's view of wl.works: its discovery, its keys, and the tokens signed out
    here (spec §5). Thread-safe: every HTTP thread of `wlx serve` checks through one."""

    def __init__(self, *, page: RigPage, issuer: str, cache: Path, fetch=fetch_json) -> None:
        self.page = page
        self.issuer = issuer
        self.cache = cache
        self._fetch = fetch
        self._lock = threading.Lock()
        self._discovery: Discovery | None = None
        self._keys: dict = {}
        self._last_refetch = float("-inf")
        #: Signed-out token ids and when each token expires (spec §5). Memory only.
        self._signed_out: dict[str, float] = {}

    @property
    def discovery(self) -> Discovery | None:
        with self._lock:
            return self._discovery

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._discovery is not None and bool(self._keys)

    def key_ids(self) -> set[str]:
        with self._lock:
            return set(self._keys)

    def load(self) -> str:
        """Discovery and keys from wl.works, else from the cache; a sentence saying which,
        for `wlx serve`'s terminal."""
        try:
            document = self._fetch(self.issuer.rstrip("/") + "/.well-known/openid-configuration")
            discovery = _discovery(document, self.issuer)
            jwks = self._fetch(discovery.jwks_uri)
            keys = _keys(jwks)
            if not keys:
                raise ValueError("wl.works' key set holds no RS256 signing key")
        except (OSError, ValueError, http.client.HTTPException) as live:
            return self._from_cache(f"{type(live).__name__}: {live}")
        _save(self.cache, document, jwks)
        with self._lock:
            self._discovery, self._keys = discovery, keys
        return f"sign-in keys from wl.works ({len(keys)})"

    def _from_cache(self, why: str) -> str:
        try:
            cached = json.loads(self.cache.read_text(encoding="utf-8"))
            discovery = _discovery(cached["discovery"], self.issuer)
            keys = _keys(cached["jwks"])
        except (OSError, ValueError, KeyError, TypeError):
            return f"{NO_KEYS} (wl.works: {why}; no usable cache at {self.cache})"
        if not keys:
            return f"{NO_KEYS} (wl.works: {why}; the cache holds no key)"
        with self._lock:
            self._discovery, self._keys = discovery, keys
        return f"sign-in keys from the cache, {len(keys)} (wl.works: {why})"

    def retry_until_ready(self, stop: threading.Event) -> None:
        """Every `RETRY_EVERY_S`, load again, until there are keys or `stop` is set."""
        while not self.ready and not stop.wait(RETRY_EVERY_S):
            self.load()
