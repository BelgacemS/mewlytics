import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.db import session_scope
from auth.models import User

PASSWORD = "correct horse"


def register(client: TestClient, username: str = "alice", password: str = PASSWORD):
    return client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )


def login(client: TestClient, username: str = "alice", password: str = PASSWORD):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register(client: TestClient) -> None:
    response = register(client, "Alice")
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert set(body) == {"id", "username"}


def test_password_stored_as_argon2id(client: TestClient) -> None:
    register(client)
    with session_scope() as session:
        stored = session.scalars(select(User.password_hash)).one()
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


def test_register_duplicate(client: TestClient) -> None:
    assert register(client, "alice").status_code == 201
    response = register(client, "ALICE", "another password")
    assert response.status_code == 409
    assert login(client, "alice").status_code == 200


def test_register_rejects_invalid_input(client: TestClient) -> None:
    for username, password in [
        ("al", PASSWORD),
        ("a" * 33, PASSWORD),
        ("alice smith", PASSWORD),
        ("alice@example.org", PASSWORD),
        ("alice", "short"),
        ("alice", "x" * 129),
    ]:
        assert register(client, username, password).status_code == 422


def test_login_returns_valid_token(client: TestClient, issuer: str) -> None:
    user_id = register(client).json()["id"]
    response = login(client, "Alice")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600

    token = body["access_token"]
    jwk = client.get("/api/auth/.well-known/jwks.json").json()["keys"][0]
    assert jwt.get_unverified_header(token) == {
        "alg": "RS256",
        "kid": jwk["kid"],
        "typ": "JWT",
    }
    claims = jwt.decode(
        token,
        jwt.PyJWK(jwk).key,
        algorithms=["RS256"],
        issuer=issuer,
        options={"require": ["iss", "sub", "iat", "exp"]},
    )
    assert claims["sub"] == str(user_id)
    assert claims["preferred_username"] == "alice"
    assert claims["exp"] - claims["iat"] == 3600


def test_login_wrong_password(client: TestClient) -> None:
    register(client)
    response = login(client, password="wrong password")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_unknown_user(client: TestClient) -> None:
    response = login(client, "nobody")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_jwks_has_no_private_members(client: TestClient) -> None:
    (key,) = client.get("/api/auth/.well-known/jwks.json").json()["keys"]
    assert set(key) == {"kty", "use", "alg", "kid", "n", "e"}
    assert (key["kty"], key["use"], key["alg"]) == ("RSA", "sig", "RS256")
