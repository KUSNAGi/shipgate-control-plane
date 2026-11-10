from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from shipgate.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def build_engine(url: str):
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 20}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=20000")
            cursor.close()
    return engine


@contextmanager
def session_scope(factory: sessionmaker) -> Iterator[Session]:
    with factory() as session:
        with session.begin():
            yield session


def make_factory(settings: Settings | None = None) -> sessionmaker:
    settings = settings or get_settings()
    return sessionmaker(bind=build_engine(settings.database_url), expire_on_commit=False)
