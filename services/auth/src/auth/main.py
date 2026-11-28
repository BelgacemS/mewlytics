from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from auth.config import Settings
from auth.db import init_db, session_scope
from auth.models import User
from auth.passwords import hash_password, verify_password
from auth.schemas import Login, Registration, TokenOut, UserOut
from auth.tokens import TokenIssuer

# Passwords are hashed and checked outside session_scope: argon2 is slow on
# purpose and must not hold the database lock.

router = APIRouter(prefix="/api/auth")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: Registration) -> UserOut:
    password_hash = hash_password(body.password)
    try:
        with session_scope() as session:
            user = User(username=body.username, password_hash=password_hash)
            session.add(user)
            session.flush()
            return UserOut.model_validate(user)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
        ) from None


@router.post("/login")
def login(body: Login, request: Request) -> TokenOut:
    """Exchange a username and password for an access token."""
    stmt = select(User.id, User.password_hash).where(User.username == body.username)
    with session_scope() as session:
        user = session.execute(stmt).one_or_none()
    # Same answer for an unknown user and a wrong password
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    issuer: TokenIssuer = request.app.state.issuer
    return TokenOut(
        access_token=issuer.issue(user.id, body.username),
        expires_in=int(issuer.ttl.total_seconds()),
    )


@router.get("/.well-known/jwks.json")
def jwks(request: Request) -> dict[str, list[dict[str, str]]]:
    """Public keys that verify the access tokens."""
    return request.app.state.issuer.jwks()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    app.state.issuer = TokenIssuer.from_pem_file(
        settings.private_key_file, settings.issuer, settings.token_ttl
    )
    init_db()
    yield


app = FastAPI(
    title="auth",
    lifespan=lifespan,
    # Under the prefix routed by the gateway
    docs_url="/api/auth/docs",
    openapi_url="/api/auth/openapi.json",
    redoc_url=None,
)
app.include_router(router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
