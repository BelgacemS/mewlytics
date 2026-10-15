from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi.testclient import TestClient

from catalog.db import session_scope
from catalog.models import Tournament


def add_tournaments(*days: int) -> None:
    with session_scope() as session:
        session.add_all(
            Tournament(
                name=f"Day {d}",
                date=datetime(2026, 9, d),
                format="M-C",
                organizer=None,
                player_count=8,
            )
            for d in days
        )


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_empty(client: TestClient) -> None:
    response = client.get("/api/catalog/tournaments")
    assert response.status_code == 200
    assert response.json() == []


def test_list_most_recent_first(client: TestClient) -> None:
    add_tournaments(13, 27, 20)
    names = [t["name"] for t in client.get("/api/catalog/tournaments").json()]
    assert names == ["Day 27", "Day 20", "Day 13"]


def test_list_pagination(client: TestClient) -> None:
    add_tournaments(13, 27, 20)
    page = client.get(
        "/api/catalog/tournaments", params={"limit": 1, "offset": 1}
    ).json()
    assert [t["name"] for t in page] == ["Day 20"]


def test_list_rejects_invalid_limit(client: TestClient) -> None:
    for limit in (0, 201):
        response = client.get("/api/catalog/tournaments", params={"limit": limit})
        assert response.status_code == 422


def test_detail_unknown(client: TestClient) -> None:
    response = client.get("/api/catalog/tournaments/999")
    assert response.status_code == 404


def test_detail(client: TestClient, tournament_id: int) -> None:
    response = client.get(f"/api/catalog/tournaments/{tournament_id}")
    assert response.status_code == 200
    body = response.json()

    assert body["name"] == "Regional"
    assert body["date"] == "2026-09-20T09:00:00"
    assert "external_id" not in body

    # Placed players first, unplaced last
    assert [e["player"] for e in body["entries"]] == ["alice", "bob", "carol"]
    alice = body["entries"][0]
    assert (alice["name"], alice["country"], alice["wins"]) == ("Alice", "FR", 2)
    assert [m["slot"] for m in alice["team"]] == [1, 2, 3, 4, 5, 6]
    assert alice["team"][0] == {
        "slot": 1,
        "species": "species-1",
        "item": None,
        "ability": None,
        "tera_type": None,
        "moves": ["protect"],
    }
    assert body["entries"][2]["team"] == []

    keys = ("phase", "round", "player1", "player2", "winner")
    assert [tuple(m[k] for k in keys) for m in body["matches"]] == [
        (1, 1, "carol", "alice", "alice"),
        (1, 2, "bob", "carol", "bob"),
        (2, 1, "alice", "bob", "alice"),
    ]
    assert {m["best_of"] for m in body["matches"]} == {3}


def test_concurrent_requests(client: TestClient, tournament_id: int) -> None:
    # More concurrent requests than the 40 threads of the threadpool
    url = f"/api/catalog/tournaments/{tournament_id}"
    with ThreadPoolExecutor(max_workers=64) as pool:
        futures = [pool.submit(client.get, url) for _ in range(200)]
        statuses = {f.result(timeout=30).status_code for f in futures}
    assert statuses == {200}
