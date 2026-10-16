from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Dialect,
    ForeignKey,
    String,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UTCDateTime(TypeDecorator[datetime]):
    """Aware datetime stored as naive UTC.

    SQLite and MySQL DATETIME keep no time zone. Naive values are rejected so
    that a local time can never be stored as if it were UTC.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(f"naive datetime {value}, expected a time zone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Limitless tournament id, null for tournaments entered by users
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    # Scheduled start
    date: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    format: Mapped[str] = mapped_column(String(16))
    organizer: Mapped[str | None] = mapped_column(String(200))
    player_count: Mapped[int]

    entries: Mapped[list[Entry]] = relationship(
        back_populates="tournament",
        cascade="all, delete-orphan",
        # NULLS LAST is not supported by MySQL
        order_by=lambda: (Entry.placing.is_(None), Entry.placing, Entry.id),
    )
    matches: Mapped[list[Match]] = relationship(
        back_populates="tournament",
        cascade="all, delete-orphan",
        order_by=lambda: (Match.phase, Match.round, Match.id),
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Limitless username, stable across tournaments
    handle: Mapped[str] = mapped_column(String(64), unique=True)


class Entry(Base):
    """A player's participation in a tournament, with the team they registered."""

    __tablename__ = "entries"
    __table_args__ = (UniqueConstraint("tournament_id", "player_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    # Display name and country can change between tournaments
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(2))
    placing: Mapped[int | None]
    wins: Mapped[int] = mapped_column(default=0)
    losses: Mapped[int] = mapped_column(default=0)
    ties: Mapped[int] = mapped_column(default=0)

    tournament: Mapped[Tournament] = relationship(back_populates="entries")
    player: Mapped[Player] = relationship()
    team: Mapped[list[TeamMember]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by=lambda: TeamMember.slot,
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("entry_id", "slot"),
        CheckConstraint("slot BETWEEN 1 AND 6", name="ck_team_members_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id"))
    slot: Mapped[int]
    # Canonical species id, mega forms included (e.g. raichu-mega-x)
    species: Mapped[str] = mapped_column(String(64))
    item: Mapped[str | None] = mapped_column(String(64))
    ability: Mapped[str | None] = mapped_column(String(64))
    tera_type: Mapped[str | None] = mapped_column(String(16))
    moves: Mapped[list[str]] = mapped_column(JSON, default=list)

    entry: Mapped[Entry] = relationship(back_populates="team")


class Match(Base):
    """A decided match. Ties, double losses and byes are not stored."""

    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("player1_id <> player2_id", name="ck_matches_players"),
        CheckConstraint(
            "winner_id IN (player1_id, player2_id)", name="ck_matches_winner"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), index=True)
    phase: Mapped[int]
    round: Mapped[int]
    # Games per match in this phase (1 for BO1, 3 for BO3)
    best_of: Mapped[int]
    player1_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    player2_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    winner_id: Mapped[int] = mapped_column(ForeignKey("players.id"))

    tournament: Mapped[Tournament] = relationship(back_populates="matches")
    player1: Mapped[Player] = relationship(foreign_keys=[player1_id])
    player2: Mapped[Player] = relationship(foreign_keys=[player2_id])
    winner: Mapped[Player] = relationship(foreign_keys=[winner_id])
