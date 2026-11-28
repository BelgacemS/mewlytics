from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from auth.config import Settings
from auth.tokens import TokenIssuer

TTL = timedelta(hours=1)


def decode(token: str, key: RSAPrivateKey) -> dict:
    return jwt.decode(token, key.public_key(), algorithms=["RS256"], issuer="iss")


def write_pkcs8(key: ec.EllipticCurvePrivateKey | RSAPrivateKey, path: Path) -> Path:
    path.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    return path


def test_expired_token_rejected(private_key: RSAPrivateKey) -> None:
    issuer = TokenIssuer(private_key, "iss", TTL)
    token = issuer.issue(1, "alice", now=datetime.now(UTC) - 2 * TTL)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode(token, private_key)


def test_token_from_another_key_rejected(
    private_key: RSAPrivateKey, other_key: RSAPrivateKey
) -> None:
    token = TokenIssuer(other_key, "iss", TTL).issue(1, "alice")
    with pytest.raises(jwt.InvalidSignatureError):
        decode(token, private_key)


def test_wrong_issuer_rejected(private_key: RSAPrivateKey) -> None:
    token = TokenIssuer(private_key, "someone-else", TTL).issue(1, "alice")
    with pytest.raises(jwt.InvalidIssuerError):
        decode(token, private_key)


def test_kid_depends_only_on_the_key(
    private_key: RSAPrivateKey, other_key: RSAPrivateKey, key_file: Path
) -> None:
    reloaded = TokenIssuer.from_pem_file(key_file, "other", 2 * TTL)
    assert reloaded.kid == TokenIssuer(private_key, "iss", TTL).kid
    assert TokenIssuer(other_key, "iss", TTL).kid != reloaded.kid


def test_non_rsa_key_rejected(tmp_path: Path) -> None:
    path = write_pkcs8(ec.generate_private_key(ec.SECP256R1()), tmp_path / "ec.pem")
    with pytest.raises(TypeError, match="RSA"):
        TokenIssuer.from_pem_file(path, "iss", TTL)


def test_short_rsa_key_rejected(tmp_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    path = write_pkcs8(key, tmp_path / "short.pem")
    with pytest.raises(ValueError, match="2048"):
        TokenIssuer.from_pem_file(path, "iss", TTL)


def test_settings_require_key_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_PRIVATE_KEY_FILE", raising=False)
    with pytest.raises(RuntimeError, match="AUTH_PRIVATE_KEY_FILE"):
        Settings.from_env()


def test_settings_reject_non_positive_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_PRIVATE_KEY_FILE", "/nonexistent")
    monkeypatch.setenv("AUTH_TOKEN_TTL_SECONDS", "0")
    with pytest.raises(RuntimeError, match="positive"):
        Settings.from_env()
