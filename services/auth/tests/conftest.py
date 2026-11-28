from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from fastapi.testclient import TestClient

from auth.db import engine
from auth.main import app
from auth.models import Base


def write_pem(key: PrivateKeyTypes, path: Path) -> Path:
    path.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    return path


@pytest.fixture(scope="session")
def issuer() -> str:
    return "test-issuer"


@pytest.fixture(scope="session")
def private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def key_file(
    private_key: RSAPrivateKey, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    return write_pem(private_key, tmp_path_factory.mktemp("keys") / "jwt.pem")


@pytest.fixture
def auth_env(
    key_file: Path, issuer: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    monkeypatch.setenv("AUTH_PRIVATE_KEY_FILE", str(key_file))
    monkeypatch.setenv("AUTH_ISSUER", issuer)
    monkeypatch.delenv("AUTH_TOKEN_TTL_SECONDS", raising=False)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(auth_env: None) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
