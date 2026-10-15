from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from catalog.db import session_scope
from catalog.models import Entry, Match, Player, TeamMember, Tournament


def make_tournament() -> Tournament:
    return Tournament(
        name="T",
        date=datetime(2026, 9, 12),
        format="M-C",
        organizer=None,
        player_count=2,
    )


def test_winner_must_be_a_player(tables: None) -> None:
    alice, bob, carol = (Player(handle=h) for h in ("alice", "bob", "carol"))
    t = make_tournament()
    t.matches = [
        Match(phase=1, round=1, best_of=3, player1=alice, player2=bob, winner=carol)
    ]
    with pytest.raises(IntegrityError), session_scope() as session:
        session.add(t)


def test_player_cannot_face_themself(tables: None) -> None:
    alice = Player(handle="alice")
    t = make_tournament()
    t.matches = [
        Match(phase=1, round=1, best_of=3, player1=alice, player2=alice, winner=alice)
    ]
    with pytest.raises(IntegrityError), session_scope() as session:
        session.add(t)


def test_one_entry_per_player_and_tournament(tables: None) -> None:
    alice = Player(handle="alice")
    t = make_tournament()
    t.entries = [
        Entry(player=alice, name="A", country=None, placing=1) for _ in range(2)
    ]
    with pytest.raises(IntegrityError), session_scope() as session:
        session.add(t)


def test_team_slot_range(tables: None) -> None:
    t = make_tournament()
    entry = Entry(player=Player(handle="alice"), name="A", country=None, placing=1)
    entry.team = [TeamMember(slot=7, species="pikachu")]
    t.entries = [entry]
    with pytest.raises(IntegrityError), session_scope() as session:
        session.add(t)


def test_foreign_keys_enforced(tables: None) -> None:
    with pytest.raises(IntegrityError), session_scope() as session:
        session.add(
            Entry(tournament_id=999, player_id=999, name="A", country=None, placing=1)
        )


def test_failed_transaction_is_rolled_back(tables: None) -> None:
    with pytest.raises(IntegrityError), session_scope() as session:
        session.add(make_tournament())
        session.flush()
        session.add(
            Entry(tournament_id=999, player_id=999, name="A", country=None, placing=1)
        )
    with session_scope() as session:
        assert session.scalars(select(Tournament)).all() == []
