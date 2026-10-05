"""`wl_xcon/signin.py`: checking a wl.works sign-in at a rig's page (b2b spec §3, §5)."""

from __future__ import annotations

import contextlib
import http.server
import json
import ssl
import threading
import urllib.error

import pytest

pytest.importorskip("jwt")

import jwt

import _tls
from _issuer import CLIENT, ISSUER, ORIGIN, PAGE, Issuer
from wl_xcon import signin
from wl_xcon.actor import Member


def test_a_rig_page_entry_is_read_as_wl_works_reads_it():
    page = signin.parse_rig_page("rig-3=https://rig-3.wl.works/")
    assert (page.name, page.page, page.origin, page.client_id, page.host) == (
        "rig-3", "https://rig-3.wl.works/", "https://rig-3.wl.works", CLIENT, "rig-3.wl.works",
    )


def test_a_page_with_a_port_keeps_it_in_the_origin_and_the_host_and_443_does_not():
    assert signin.parse_rig_page("rig-3=https://127.0.0.1:8443/").origin == "https://127.0.0.1:8443"
    assert signin.parse_rig_page("rig-3=https://127.0.0.1:8443/").host == "127.0.0.1:8443"
    assert signin.parse_rig_page("rig-3=https://Rig-3.WL.works:443/").origin == "https://rig-3.wl.works"


@pytest.mark.parametrize(
    "text, says",
    [
        ("https://rig-3.wl.works/", '"="'),
        ("Rig3=https://rig-3.wl.works/", "lower-case"),
        ("rig--3=https://rig-3.wl.works/", "lower-case"),
        ("r" * 33 + "=https://rig-3.wl.works/", "lower-case"),
        ("rig-3=http://rig-3.wl.works/", "absolute https address"),
        ("rig-3=https://u:p@rig-3.wl.works/", "user name"),
        ("rig-3=https://rig-3.wl.works/#x", "fragment"),
        ("rig-3=https://rig-3.wl.works/a,b", "comma"),
        ("rig-3=not a url", "absolute https address"),
        ("rig-3=https://rig-3.wl.works:abc/", "port"),
        ("rig-3=https://rig-3.wl.works:99999/", "port"),
    ],
)
def test_a_rig_page_wl_works_would_refuse_is_refused_here(text, says):
    with pytest.raises(ValueError) as refused:
        signin.parse_rig_page(text)
    assert says in str(refused.value)


def _checker(tmp_path, issuer: Issuer) -> signin.Checker:
    return signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"),
        issuer=ISSUER,
        cache=tmp_path / "wl-works.json",
        fetch=issuer.fetch,
    )


def test_load_reads_discovery_and_keys_from_wl_works_and_caches_both(tmp_path):
    issuer = Issuer()
    checker = _checker(tmp_path, issuer)
    said = checker.load()
    assert checker.ready and "from wl.works" in said
    assert checker.discovery.token_endpoint == f"{ISSUER}/oauth2/token"
    assert checker.discovery.token_origin == "https://wl.works"
    cached = json.loads((tmp_path / "wl-works.json").read_text())
    assert cached["discovery"]["issuer"] == ISSUER and cached["jwks"]["keys"]


def test_load_falls_back_to_the_cache_when_wl_works_is_unreachable(tmp_path):
    issuer = Issuer()
    _checker(tmp_path, issuer).load()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    said = checker.load()
    assert checker.ready and "from the cache" in said


def test_with_no_wl_works_and_no_cache_the_rig_holds_no_keys(tmp_path):
    issuer = Issuer()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    said = checker.load()
    assert not checker.ready and checker.discovery is None
    assert signin.NO_KEYS in said


def test_a_discovery_naming_another_issuer_is_refused_and_not_cached(tmp_path):
    issuer = Issuer(issuer="https://wl.works")  # a different issuer string
    checker = signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"),
        issuer=ISSUER,
        cache=tmp_path / "wl-works.json",
        fetch=lambda url: issuer.discovery() if "openid" in url else issuer.jwks(),
    )
    said = checker.load()
    assert not checker.ready and signin.NO_KEYS in said
    assert not (tmp_path / "wl-works.json").exists()


@pytest.mark.parametrize(
    "endpoint",
    ["https://wl.works;img-src */x/token", "https://wl.works img-src/x", "https://u@wl.works/x", "https:///x"],
)
def test_a_discovery_endpoint_with_more_than_a_host_and_a_port_is_refused(tmp_path, endpoint):
    issuer = Issuer()
    document = {**issuer.discovery(), "token_endpoint": endpoint}
    checker = signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"),
        issuer=ISSUER,
        cache=tmp_path / "wl-works.json",
        fetch=lambda url: document if "openid" in url else issuer.jwks(),
    )
    said = checker.load()
    assert not checker.ready and checker.discovery is None and signin.NO_KEYS in said
    assert not (tmp_path / "wl-works.json").exists()


def test_a_cache_naming_another_issuer_is_not_used(tmp_path):
    (tmp_path / "wl-works.json").write_text(
        json.dumps({"discovery": {**Issuer().discovery(), "issuer": "https://elsewhere"}, "jwks": Issuer().jwks()})
    )
    issuer = Issuer()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    checker.load()
    assert not checker.ready


def test_only_rsa_signing_keys_are_kept(tmp_path):
    issuer = Issuer()
    extra = (
        {"kty": "EC", "kid": "ec", "crv": "P-256", "x": "AA", "y": "AA"},
        {**issuer.jwks()["keys"][0], "kid": "enc", "use": "enc"},
        {**issuer.jwks()["keys"][0], "kid": "hs", "alg": "HS256"},
    )
    checker = signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"), issuer=ISSUER, cache=tmp_path / "c.json",
        fetch=lambda url: issuer.discovery() if "openid" in url else issuer.jwks(*extra),
    )
    checker.load()
    assert checker.key_ids() == {issuer.kid}


def test_fetch_json_refuses_plain_http():
    with pytest.raises(ValueError):
        signin.fetch_json("http://wl.works/api/auth/jwks")


def test_retry_until_ready_loads_once_wl_works_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(signin, "RETRY_EVERY_S", 0.05)
    issuer = Issuer()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    checker.load()
    assert not checker.ready
    stop = threading.Event()
    thread = threading.Thread(target=checker.retry_until_ready, args=(stop,), daemon=True)
    thread.start()
    try:
        issuer.down = False
        for _ in range(100):
            if checker.ready:
                break
            stop.wait(0.05)
        assert checker.ready
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()


@contextlib.contextmanager
def _loopback(tmp_path, status=200, body=None):
    """A real https server on 127.0.0.1 (certificate from `_tls`); yields (url, material).
    Answers `status` with `body` (bytes; default a small JSON object)."""
    material = _tls.material(tmp_path)
    payload = json.dumps({"issuer": ISSUER, "n": 1}).encode() if body is None else body

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 -- the stdlib's name
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    served = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    served.load_cert_chain(str(material["cert"]), str(material["key"]))
    server.socket = served.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_address[1]}/doc", material
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_fetch_json_reads_a_document_over_a_real_loopback_https_server(tmp_path):
    with _loopback(tmp_path) as (url, material):
        assert signin.fetch_json(url, context=_tls.client_context(material["ca"])) == {"issuer": ISSUER, "n": 1}


def _reason(err: BaseException) -> BaseException:
    return err.reason if isinstance(err, urllib.error.URLError) else err


def test_fetch_json_refuses_a_certificate_from_an_authority_it_does_not_trust(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    with _loopback(tmp_path) as (url, _material):
        stranger = _tls.client_context(_tls.material(other)["ca"])
        for context in (stranger, None):  # an unrelated CA, and the system's defaults
            with pytest.raises((ssl.SSLCertVerificationError, urllib.error.URLError)) as refused:
                signin.fetch_json(url, context=context)
            assert isinstance(_reason(refused.value), ssl.SSLCertVerificationError)


@pytest.mark.parametrize(
    "status, body, says",
    [
        (201, b"{}", "answered 201"),
        (200, b"not json", None),
        (200, b"[1, 2]", "did not answer a JSON object"),
        (200, b" " * (signin.FETCH_LIMIT + 1), "more than"),
    ],
)
def test_fetch_json_refuses_what_is_not_one_small_json_object(tmp_path, status, body, says):
    with _loopback(tmp_path, status=status, body=body) as (url, material):
        context = _tls.client_context(material["ca"])
        with pytest.raises(ValueError) as refused:  # json.JSONDecodeError is a ValueError
            signin.fetch_json(url, context=context)
        if says:
            assert says in str(refused.value)


def test_a_key_with_no_key_id_is_dropped(tmp_path):
    issuer = Issuer()
    nameless = {k: v for k, v in issuer.jwks()["keys"][0].items() if k != "kid"}
    checker = signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"), issuer=ISSUER, cache=tmp_path / "c.json",
        fetch=lambda url: issuer.discovery() if "openid" in url else issuer.jwks(nameless),
    )
    checker.load()
    assert checker.key_ids() == {issuer.kid}


def test_a_cache_that_is_not_json_is_not_used_when_wl_works_is_unreachable(tmp_path):
    (tmp_path / "wl-works.json").write_text("{not json")
    issuer = Issuer()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    assert signin.NO_KEYS in checker.load() and not checker.ready


def test_a_cache_that_cannot_be_written_does_not_lose_the_live_keys(tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    checker = signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"), issuer=ISSUER,
        cache=blocker / "wl-works.json", fetch=Issuer().fetch,
    )
    said = checker.load()
    assert checker.ready and "not cached" in said and "from wl.works" in said


def _ready(tmp_path, issuer=None):
    issuer = issuer or Issuer()
    checker = _checker(tmp_path, issuer)
    checker.load()
    return checker, issuer


class _Header(str):
    """An `Authorization` value that prints as `'Bearer <token>'`, so a pytest traceback
    (locals, arguments, `-vv`) never shows a token."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "'Bearer <token>'"


def _bearer(token: str) -> str:
    __tracebackhide__ = True
    return _Header(f"Bearer {token}")


def test_a_good_token_names_its_member(tmp_path):
    checker, issuer = _ready(tmp_path)
    accepted = checker.check(_bearer(issuer.mint(jti="j-1")))
    assert accepted.member == Member(name="Jake Westerberg", account="user-1", issuer=ISSUER, token_id="j-1")
    assert accepted.expires_at > 0


def _refused(checker, header) -> signin.Refused:
    __tracebackhide__ = True
    with pytest.raises(signin.Refused) as refused:
        checker.check(header)
    return refused.value


@pytest.mark.parametrize(
    "header",
    [None, "", "Basic abc", "Bearer", "Bearer " + "x" * 9000],
    ids=["absent", "empty", "basic", "no-token", "over-the-limit"],
)
def test_no_token_is_refused_asking_for_a_sign_in(tmp_path, header):
    checker, _ = _ready(tmp_path)
    refused = _refused(checker, header)
    assert (refused.reason, refused.said) == ("no_token", signin.NO_TOKEN)


@pytest.mark.parametrize(
    "mint, reason",
    [
        (dict(exp_in=-120), "expired"),
        (dict(iat_in=600), "clock"),
        (dict(aud="https://rig-4.wl.works"), "other_rig"),
        (dict(aud=[ORIGIN, "https://wl.works/api/auth/oauth2/userinfo"]), "other_rig"),
        (dict(azp="wl-works-rig-rig-4"), "other_rig"),
        (dict(iss="https://wl.works"), "not_accepted"),
        (dict(iss="https://wl.works/api/auth/"), "not_accepted"),
        (dict(typ="JWT"), "not_accepted"),
        (dict(kid="nobody"), "not_accepted"),
        (dict(drop=("jti",)), "not_accepted"),
        (dict(drop=("sub",)), "not_accepted"),
        (dict(name=""), "not_accepted"),
        (dict(name=None), "not_accepted"),
        (dict(name="x" * 201), "not_accepted"),
        (dict(name="Jake\x00Westerberg"), "not_accepted"),
        (dict(client_id="wl-works-rig-rig-4"), "other_rig"),
        (dict(drop=("azp",)), "other_rig"),
        (dict(drop=("exp",)), "not_accepted"),
        (dict(drop=("iat",)), "not_accepted"),
    ],
)
def test_each_check_refuses_on_its_own(tmp_path, mint, reason):
    checker, issuer = _ready(tmp_path)
    assert _refused(checker, _bearer(issuer.mint(**mint))).reason == reason


def test_a_token_signed_by_another_key_is_refused(tmp_path):
    checker, issuer = _ready(tmp_path)
    forger = Issuer()
    assert _refused(checker, _bearer(forger.mint(kid=issuer.kid))).reason == "not_accepted"


def _hs256(claims: dict, secret: bytes, kid: str) -> str:
    """An HS256 token built by hand: PyJWT itself refuses to use a PEM public key as an
    HMAC secret, so the attack has to be assembled the way an attacker would."""
    import base64
    import hashlib
    import hmac

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    head = b64(json.dumps({"alg": "HS256", "typ": "at+jwt", "kid": kid}).encode())
    body = b64(json.dumps(claims).encode())
    signature = b64(hmac.new(secret, head + b"." + body, hashlib.sha256).digest())
    return (head + b"." + body + b"." + signature).decode("ascii")


def test_alg_none_and_hs256_keyed_on_the_public_key_are_refused(tmp_path):
    """The algorithm-confusion attacks: an unsigned token, and an HMAC whose secret is
    the published public key."""
    from cryptography.hazmat.primitives import serialization

    checker, issuer = _ready(tmp_path)
    public = issuer.key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    claims = jwt.decode(issuer.mint(), options={"verify_signature": False})
    unsigned = jwt.encode(claims, None, algorithm="none", headers={"typ": "at+jwt", "kid": issuer.kid})
    assert _refused(checker, _bearer(unsigned)).reason == "not_accepted"
    assert _refused(checker, _bearer(_hs256(claims, public, issuer.kid))).reason == "not_accepted"


def test_an_unknown_key_id_fetches_the_key_set_again_at_most_once_a_minute(tmp_path):
    checker, issuer = _ready(tmp_path)
    fetched = len(issuer.fetched)
    _refused(checker, _bearer(issuer.mint(kid="new")))
    _refused(checker, _bearer(issuer.mint(kid="newer")))
    assert len(issuer.fetched) == fetched + 1


def test_a_key_wl_works_rotated_in_is_picked_up(tmp_path):
    checker, issuer = _ready(tmp_path)
    issuer.kid = "rotated"
    accepted = checker.check(_bearer(issuer.mint()))
    assert accepted.member.name == "Jake Westerberg"


def test_a_rotated_in_key_set_is_cached_beside_the_discovery_document(tmp_path):
    checker, issuer = _ready(tmp_path)
    issuer.kid = "rotated"
    checker.check(_bearer(issuer.mint()))
    cached = json.loads((tmp_path / "wl-works.json").read_text())
    assert [key["kid"] for key in cached["jwks"]["keys"]] == ["rotated"]
    assert cached["discovery"]["issuer"] == ISSUER
    # A restart with wl.works unreachable finds the rotated key in the cache.
    issuer.down = True
    restarted = _checker(tmp_path, issuer)
    restarted.load()
    assert restarted.key_ids() == {"rotated"}


def test_a_rotated_in_key_is_kept_when_the_cache_cannot_be_written(tmp_path):
    issuer = Issuer()
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    checker = signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"), issuer=ISSUER,
        cache=blocker / "wl-works.json", fetch=issuer.fetch,
    )
    assert "not cached" in checker.load()
    issuer.kid = "rotated"
    accepted = checker.check(_bearer(issuer.mint(jti="j-9")))
    assert accepted.member.token_id == "j-9"
    assert checker.key_ids() == {"rotated"}


def test_a_signed_out_token_is_refused_here_and_another_is_not(tmp_path):
    checker, issuer = _ready(tmp_path)
    first, second = issuer.mint(jti="j-1"), issuer.mint(jti="j-2")
    checker.sign_out(_bearer(first))
    assert _refused(checker, _bearer(first)).reason == "signed_out"
    accepted = checker.check(_bearer(second))
    assert accepted.member.token_id == "j-2"


def test_signing_out_a_token_that_does_not_check_out_does_nothing(tmp_path):
    checker, issuer = _ready(tmp_path)
    checker.sign_out("Bearer junk")
    checker.sign_out(None)
    accepted = checker.check(_bearer(issuer.mint()))
    assert accepted.member.name == "Jake Westerberg"


def test_with_no_keys_every_token_is_refused_saying_so(tmp_path):
    issuer = Issuer()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    checker.load()
    refused = _refused(checker, _bearer(issuer.mint()))
    assert (refused.reason, refused.said) == ("no_keys", signin.NO_KEYS)


def test_no_refusal_echoes_the_token(tmp_path):
    checker, issuer = _ready(tmp_path)
    token = issuer.mint(exp_in=-120)
    refused = _refused(checker, _bearer(token))
    leaked = token in refused.said or token in str(refused)
    assert not leaked


def test_a_signed_out_token_stays_refused_through_the_leeway_after_its_expiry(tmp_path):
    """`exp` 30 s ago is inside `LEEWAY_S`, so PyJWT still accepts it; the signed-out
    entry must outlive `exp` by the same leeway or the sign-out would lapse early."""
    checker, issuer = _ready(tmp_path)
    token = _bearer(issuer.mint(jti="j-1", exp_in=-30))
    accepted = checker.check(token)
    assert accepted.member.token_id == "j-1"
    checker.sign_out(token)
    assert _refused(checker, token).reason == "signed_out"
