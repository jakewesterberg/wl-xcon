"""A fake wl.works for the sign-in tests (b2b spec §8): an RSA key generated at test
time, a discovery document and key set shaped like the live ones read 2026-10-02, and
access tokens minted the way wl.works mints a rig's (`createJwtAccessToken` in
`@better-auth/oauth-provider` 1.7.1: header alg RS256, typ at+jwt, kid; claims sub, aud,
client_id, azp, scope, iss, iat, exp, jti, plus wl.works' `name`). Never on the network."""

from __future__ import annotations

import base64
import secrets
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://wl.works/api/auth"
PAGE = "https://rig-3.wl.works/"
ORIGIN = "https://rig-3.wl.works"
CLIENT = "wl-works-rig-rig-3"


def _b64(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class Issuer:
    def __init__(self, issuer: str = ISSUER, kid: str = "test-key-1") -> None:
        self.issuer = issuer
        self.kid = kid
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.fetched: list[str] = []
        #: Set by a test to make `fetch` raise, as an unreachable wl.works would.
        self.down = False

    def pem(self) -> bytes:
        return self.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def discovery(self) -> dict:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/oauth2/authorize",
            "token_endpoint": f"{self.issuer}/oauth2/token",
            "jwks_uri": f"{self.issuer}/jwks",
            "code_challenge_methods_supported": ["S256"],
        }

    def jwks(self, *extra: dict) -> dict:
        numbers = self.key.public_key().public_numbers()
        mine = {"kty": "RSA", "alg": "RS256", "kid": self.kid, "n": _b64(numbers.n), "e": _b64(numbers.e)}
        return {"keys": [mine, *extra]}

    def fetch(self, url: str) -> dict:
        self.fetched.append(url)
        if self.down:
            raise OSError("wl.works is unreachable (test)")
        if url == f"{self.issuer}/.well-known/openid-configuration":
            return self.discovery()
        if url == f"{self.issuer}/jwks":
            return self.jwks()
        raise OSError(f"no such document: {url}")

    def mint(
        self,
        *,
        aud: object = ORIGIN,
        azp: str = CLIENT,
        name: object = "Jake Westerberg",
        sub: object = "user-1",
        jti: object | None = None,
        exp_in: float = 3600,
        iat_in: float = 0,
        iss: str | None = None,
        typ: str = "at+jwt",
        kid: str | None = None,
        drop: tuple = (),
        key=None,
        algorithm: str = "RS256",
    ) -> str:
        now = time.time()
        claims = {
            "sub": sub, "aud": aud, "client_id": azp, "azp": azp, "scope": "offline_access",
            "iss": self.issuer if iss is None else iss, "iat": int(now + iat_in),
            "exp": int(now + exp_in), "jti": jti or secrets.token_hex(16), "name": name,
        }
        for claim in drop:
            claims.pop(claim)
        headers = {"typ": typ, "kid": self.kid if kid is None else kid}
        return jwt.encode(claims, self.pem() if key is None else key, algorithm=algorithm, headers=headers)
