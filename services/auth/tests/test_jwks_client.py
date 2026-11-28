import socket
import threading
import time
from collections.abc import Iterator

import httpx2
import jwt
import pytest
import uvicorn

from auth.main import app


@pytest.fixture
def server_url(auth_env: None) -> Iterator[str]:
    """The app served by uvicorn on a free port, for clients that do real HTTP."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]})
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


def test_pyjwkclient_verifies_tokens(server_url: str, issuer: str) -> None:
    credentials = {"username": "alice", "password": "correct horse"}
    with httpx2.Client(base_url=server_url) as http:
        assert http.post("/api/auth/register", json=credentials).status_code == 201
        token = http.post("/api/auth/login", json=credentials).json()["access_token"]

    client = jwt.PyJWKClient(f"{server_url}/api/auth/.well-known/jwks.json")
    signing_key = client.get_signing_key_from_jwt(token)
    claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], issuer=issuer)
    assert claims["preferred_username"] == "alice"
