"""Database engine and session factory.

Schema creation is done exclusively by SQLAlchemy (`Base.metadata.create_all`)
on application startup; there is no init.sql so the two paths can never drift.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


_connect_args = {}
_engine_kwargs = {}

if settings.sqlalchemy_url.startswith("sqlite"):
    # SQLite (tests): allow cross-thread usage and share one in-memory connection.
    _connect_args["check_same_thread"] = False
    _engine_kwargs["poolclass"] = __import__(
        "sqlalchemy.pool", fromlist=["StaticPool"]
    ).StaticPool
else:
    _engine_kwargs["pool_pre_ping"] = True

engine = create_engine(
    settings.sqlalchemy_url,
    connect_args=_connect_args,
    **_engine_kwargs,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    """FastAPI dependency yielding a short-lived session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
