from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from mogul.config import get_settings


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
        yield session
