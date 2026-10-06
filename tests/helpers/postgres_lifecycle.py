from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.engine.url import make_url


def _as_url(url: str | URL) -> URL:
    parsed = make_url(url) if not isinstance(url, URL) else url
    if parsed.drivername == "postgresql":
        return parsed.set(drivername="postgresql+psycopg2")
    return parsed


def _postgres_admin_engine(url: str | URL) -> Engine:
    parsed = _as_url(url)
    return create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")


def database_exists(url: str | URL) -> bool:
    parsed = _as_url(url)
    engine = _postgres_admin_engine(parsed)
    try:
        with engine.connect() as conn:
            return bool(
                conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": parsed.database},
                )
            )
    finally:
        engine.dispose()


def create_database(url: str | URL) -> None:
    parsed = _as_url(url)
    engine = _postgres_admin_engine(parsed)
    try:
        with engine.connect() as conn:
            ident = conn.dialect.identifier_preparer.quote(parsed.database)
            conn.execute(text(f"CREATE DATABASE {ident}"))
    finally:
        engine.dispose()


def drop_database(url: str | URL) -> None:
    parsed = _as_url(url)
    engine = _postgres_admin_engine(parsed)
    try:
        with engine.connect() as conn:
            ident = conn.dialect.identifier_preparer.quote(parsed.database)
            conn.execute(text(f"DROP DATABASE {ident}"))
    finally:
        engine.dispose()
