from datetime import datetime

from pydantic import AliasPath, BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TournamentSummary(Schema):
    id: int
    name: str
    date: datetime
    format: str
    organizer: str | None
    player_count: int


class TeamMemberOut(Schema):
    slot: int
    species: str
    item: str | None
    ability: str | None
    tera_type: str | None
    moves: list[str]


class EntryOut(Schema):
    player: str = Field(validation_alias=AliasPath("player", "handle"))
    name: str
    country: str | None
    placing: int | None
    wins: int
    losses: int
    ties: int
    team: list[TeamMemberOut]


class MatchOut(Schema):
    phase: int
    round: int
    best_of: int
    player1: str = Field(validation_alias=AliasPath("player1", "handle"))
    player2: str = Field(validation_alias=AliasPath("player2", "handle"))
    winner: str = Field(validation_alias=AliasPath("winner", "handle"))


class TournamentDetail(TournamentSummary):
    entries: list[EntryOut]
    matches: list[MatchOut]
