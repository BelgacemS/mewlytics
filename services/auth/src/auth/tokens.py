import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from jwt.algorithms import RSAAlgorithm

ALGORITHM = "RS256"


def jwk_thumbprint(jwk: dict[str, Any]) -> str:
    """RFC 7638 thumbprint of an RSA public JWK, used as its key id.

    It only depends on the key, so the kid stays the same across restarts and
    changes when the key is rotated.
    """
    members = {name: jwk[name] for name in ("e", "kty", "n")}
    canonical = json.dumps(members, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class TokenIssuer:
    """Signs access tokens with one RSA key and publishes its public half."""

    def __init__(self, private_key: RSAPrivateKey, issuer: str, ttl: timedelta):
        if private_key.key_size < 2048:
            raise ValueError("RSA keys shorter than 2048 bits are not accepted")
        self._private_key = private_key
        self.issuer = issuer
        self.ttl = ttl
        public = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
        self.kid = jwk_thumbprint(public)
        self._jwk = {
            "kty": "RSA",
            "use": "sig",
            "alg": ALGORITHM,
            "kid": self.kid,
            "n": public["n"],
            "e": public["e"],
        }

    @classmethod
    def from_pem_file(cls, path: Path, issuer: str, ttl: timedelta) -> "TokenIssuer":
        key = load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, RSAPrivateKey):
            raise TypeError(f"{path} does not hold an RSA private key")
        return cls(key, issuer, ttl)

    def issue(self, user_id: int, username: str, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        claims = {
            "iss": self.issuer,
            "sub": str(user_id),
            "preferred_username": username,
            "iat": now,
            "exp": now + self.ttl,
        }
        return jwt.encode(
            claims, self._private_key, algorithm=ALGORITHM, headers={"kid": self.kid}
        )

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        return {"keys": [dict(self._jwk)]}
