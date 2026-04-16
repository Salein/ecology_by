from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_ENGINE = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)
SessionLocal = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False, future=True)


def get_db_session() -> Session:
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_db_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
