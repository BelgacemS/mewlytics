from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from catalog.db import engine, init_db, session_scope
from catalog.main import app
from catalog.models import Base, Entry, Match, Player, TeamMember, Tournament


@pytest.fixture
def tables() -> Iterator[None]:
    init_db()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(tables: None) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def tournament_id(tables: None) -> int:
    """One tournament with three players, alice's full team and three matches.

    Rows are inserted out of order to check the ordering done by the API.
    """
    with session_scope() as session:
        alice, bob, carol = (Player(handle=h) for h in ("alice", "bob", "carol"))
        t = Tournament(
            external_id="limitless-1",
            name="Regional",
            date=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
            format="M-C",
            organizer="Some league",
            player_count=3,
        )
        t.entries = [
            Entry(player=carol, name="Carol", country=None, placing=None, losses=2),
            Entry(player=bob, name="Bob", country="DE", placing=2, wins=1, losses=1),
            Entry(
                player=alice,
                name="Alice",
                country="FR",
                placing=1,
                wins=2,
                team=[
                    TeamMember(slot=s, species=f"species-{s}", moves=["protect"])
                    for s in (6, 5, 4, 3, 2, 1)
                ],
            ),
        ]
        t.matches = [
            Match(
                phase=2, round=1, best_of=3, player1=alice, player2=bob, winner=alice
            ),
            Match(phase=1, round=2, best_of=3, player1=bob, player2=carol, winner=bob),
            Match(
                phase=1, round=1, best_of=3, player1=carol, player2=alice, winner=alice
            ),
        ]
        session.add(t)
        session.flush()
        return t.id
