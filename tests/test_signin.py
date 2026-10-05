"""`wl_xcon/signin.py`: checking a wl.works sign-in at a rig's page (b2b spec §3, §5)."""

from __future__ import annotations

import http.server
import json
import ssl
import threading

import pytest

pytest.importorskip("jwt")

import _tls
from _issuer import CLIENT, ISSUER, ORIGIN, PAGE, Issuer
from wl_xcon import signin


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
        ("rig-3=http://rig-3.wl.works/", "https"),
        ("rig-3=https://u:p@rig-3.wl.works/", "user name"),
        ("rig-3=https://rig-3.wl.works/#x", "fragment"),
        ("rig-3=https://rig-3.wl.works/a,b", "comma"),
        ("rig-3=not a url", "https"),
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
    assert checker.ready and "cache" in said


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


def test_fetch_json_reads_a_document_over_a_real_loopback_https_server(tmp_path):
    material = _tls.material(tmp_path)
    document = {"issuer": ISSUER, "n": 1}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 -- the stdlib's name
            body = json.dumps(document).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    served = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    served.load_cert_chain(str(material["cert"]), str(material["key"]))
    server.socket = served.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"https://127.0.0.1:{server.server_address[1]}/doc"
        assert signin.fetch_json(url, context=_tls.client_context(material["ca"])) == document
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
