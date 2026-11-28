"""Engine and sessions, on an in-memory SQLite database.

StaticPool hands the same connection to every session, which is only safe if
sessions never overlap, so each one is opened under a global lock.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from auth.models import Base

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(engine)
_lock = threading.Lock()


def init_db() -> None:
    with _lock:
        Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a session in a transaction, committed on exit, rolled back on error.

    Use it inside the endpoint body rather than as a yield dependency: FastAPI
    runs the dependency and the endpoint in different threadpool calls, so
    requests waiting for the lock could take every thread and starve the one
    holding it.
    """
    with _lock, SessionLocal.begin() as session:
        yield session
