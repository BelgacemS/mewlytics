from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from catalog.db import init_db, session_scope
from catalog.models import Entry, Match, Tournament
from catalog.schemas import TournamentDetail, TournamentSummary

# Endpoints are plain `def`: FastAPI runs them in its threadpool, and the ORM
# objects are converted to schemas inside the session, never after it closes.

router = APIRouter(prefix="/api/catalog")


@router.get("/tournaments")
def list_tournaments(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TournamentSummary]:
    """Tournaments, most recent first."""
    stmt = (
        select(Tournament)
        .order_by(Tournament.date.desc(), Tournament.id.desc())
        .limit(limit)
        .offset(offset)
    )
    with session_scope() as session:
        return [TournamentSummary.model_validate(t) for t in session.scalars(stmt)]


@router.get("/tournaments/{tournament_id}")
def get_tournament(tournament_id: int) -> TournamentDetail:
    """A tournament with its standings, teams and matches."""
    stmt = (
        select(Tournament)
        .where(Tournament.id == tournament_id)
        .options(
            selectinload(Tournament.entries).options(
                selectinload(Entry.player), selectinload(Entry.team)
            ),
            selectinload(Tournament.matches).options(
                selectinload(Match.player1),
                selectinload(Match.player2),
                selectinload(Match.winner),
            ),
        )
    )
    with session_scope() as session:
        tournament = session.scalar(stmt)
        if tournament is None:
            raise HTTPException(status_code=404, detail="Tournament not found")
        return TournamentDetail.model_validate(tournament)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="catalog",
    lifespan=lifespan,
    # Under the prefix routed by the gateway
    docs_url="/api/catalog/docs",
    openapi_url="/api/catalog/openapi.json",
    redoc_url=None,
)
app.include_router(router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
