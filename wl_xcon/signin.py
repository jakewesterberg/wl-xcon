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
    try:
        port = parts.port
    except ValueError:
        raise ValueError(f"{shape}; its port is not a number from 0 to 65535") from None
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


#: Seconds of clock leeway on `exp` and `iat`. Housekeeping (spec §5), not a
#: measurement: the rig keeps time from wl-works' NTP server (ADR-0009).
LEEWAY_S = 60
#: The longest `Authorization` value read, in bytes. A bound on one header's reach,
#: not a rule about wl.works: its tokens are about a kilobyte.
TOKEN_LIMIT = 8192
#: wl.works' access-token type (`JWT_ACCESS_TOKEN_TYPE`), and RFC 9068 §2.1's long form.
ACCESS_TOKEN_TYPES = frozenset({"at+jwt", "application/at+jwt"})

#: The refusals (spec §5): each a sentence for the page, and a word for its script.
NO_TOKEN = "sign in with wl.works to use the controls"
SIGNED_OUT = "this sign-in was signed out here; sign in again"
EXPIRED = "your sign-in has expired; sign in again"
OTHER_RIG = "this sign-in is for another rig"
CLOCK = "the rig's clock and this sign-in disagree; check the rig's time"
NOT_ACCEPTED = "this is not a wl.works sign-in the rig accepts"


class Refused(Exception):
    """A token this rig does not accept: `said` for a person, `reason` for the page's
    script (the plan's Ruling 8). Never carries the token."""

    def __init__(self, reason: str, said: str) -> None:
        super().__init__(said)
        self.reason = reason
        self.said = said


@dataclass(frozen=True, slots=True)
class Accepted:
    """A token that checked out: who it names, and when it expires (POSIX seconds)."""

    member: actors.Member
    expires_at: float


def _bearer(authorization: str | None) -> str:
    if not authorization or len(authorization) > TOKEN_LIMIT:
        raise Refused("no_token", NO_TOKEN)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Refused("no_token", NO_TOKEN)
    return token.strip()


def _claim(claims: dict, name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > actors.TEXT_LIMIT or not value.isprintable():
        raise Refused("not_accepted", NOT_ACCEPTED)
    return value


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
        #: The discovery document as accepted (live or cached), so a key set fetched
        #: again later can be cached beside it.
        self._document: dict | None = None
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
        with self._lock:
            self._discovery, self._keys, self._document = discovery, keys, document
        try:
            _save(self.cache, document, jwks)
        except OSError as err:
            # Live keys are good whether or not they can be kept; say why they were not.
            return f"sign-in keys from wl.works ({len(keys)}); not cached: {type(err).__name__} {err.strerror or ''}".rstrip()
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
            self._discovery, self._keys, self._document = discovery, keys, cached["discovery"]
        return f"sign-in keys from the cache, {len(keys)} (wl.works: {why})"

    def retry_until_ready(self, stop: threading.Event) -> None:
        """Every `RETRY_EVERY_S`, load again, until there are keys or `stop` is set."""
        while not self.ready and not stop.wait(RETRY_EVERY_S):
            self.load()

    def check(self, authorization: str | None) -> Accepted:
        """Spec §5's checks, in its order. Raises `Refused`."""
        token = _bearer(authorization)
        with self._lock:
            discovery = self._discovery
            ready = discovery is not None and bool(self._keys)
        if not ready:
            raise Refused("no_keys", NO_KEYS)
        try:
            head = jwt.get_unverified_header(token)
        except jwt.exceptions.PyJWTError:
            raise Refused("not_accepted", NOT_ACCEPTED) from None
        typ = head.get("typ")
        if head.get("alg") != "RS256" or not isinstance(typ, str) or typ.lower() not in ACCESS_TOKEN_TYPES:
            raise Refused("not_accepted", NOT_ACCEPTED)
        key = self._key(head.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.page.origin,
                issuer=discovery.issuer,
                leeway=LEEWAY_S,
                options={"require": ["exp", "iat", "sub", "aud", "iss", "jti"], "strict_aud": True},
            )
        except jwt.exceptions.ExpiredSignatureError:
            raise Refused("expired", EXPIRED) from None
        except jwt.exceptions.ImmatureSignatureError:
            raise Refused("clock", CLOCK) from None
        except jwt.exceptions.InvalidAudienceError:
            raise Refused("other_rig", OTHER_RIG) from None
        except jwt.exceptions.PyJWTError:
            raise Refused("not_accepted", NOT_ACCEPTED) from None
        # Again, exactly: PyJWT 2.10.0 compared a string issuer as a substring (spec §5).
        if claims.get("iss") != discovery.issuer:
            raise Refused("not_accepted", NOT_ACCEPTED)
        if claims.get("azp") != self.page.client_id or claims.get("client_id", self.page.client_id) != self.page.client_id:
            raise Refused("other_rig", OTHER_RIG)
        member = actors.Member(
            name=_claim(claims, "name"),
            account=_claim(claims, "sub"),
            issuer=claims["iss"],
            token_id=_claim(claims, "jti"),
        )
        now = time.time()
        with self._lock:
            self._signed_out = {jti: until for jti, until in self._signed_out.items() if until + LEEWAY_S > now}
            if member.token_id in self._signed_out:
                raise Refused("signed_out", SIGNED_OUT)
        return Accepted(member, float(claims["exp"]))

    def _key(self, kid: object):
        """The key `kid` names; an unknown one fetches the key set again, at most once
        every `REFETCH_EVERY_S`, so a key wl.works rotated in is found and junk ids cannot
        make the rig fetch on every request."""
        if not isinstance(kid, str):
            raise Refused("not_accepted", NOT_ACCEPTED)
        with self._lock:
            key = self._keys.get(kid)
            due = time.monotonic() - self._last_refetch >= REFETCH_EVERY_S
            if key is None and due:
                self._last_refetch = time.monotonic()
            discovery, document = self._discovery, self._document
        if key is None and due and discovery is not None:
            try:
                jwks = self._fetch(discovery.jwks_uri)
                keys = _keys(jwks)
            except (OSError, ValueError, http.client.HTTPException):
                keys = {}
            if keys:
                with self._lock:
                    self._keys = keys
                key = keys.get(kid)
                if document is not None:
                    try:
                        _save(self.cache, document, jwks)
                    except OSError:
                        pass  # New keys are good whether or not they can be kept.
        if key is None:
            raise Refused("not_accepted", NOT_ACCEPTED)
        return key

    def sign_out(self, authorization: str | None) -> None:
        """Refuse this token here for the rest of its hour (spec §4, §5). A token that
        does not check out needs no signing out."""
        try:
            accepted = self.check(authorization)
        except Refused:
            return
        with self._lock:
            self._signed_out[accepted.member.token_id] = accepted.expires_at
