from contextlib import contextmanager

import psycopg2

from app.models import db


@contextmanager
def session_guard(session, close=True):
    try:
        yield session
        session.flush()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if close:
            session.close()


@contextmanager
def multi_session_guard(session_list):
    yield session_list
    for session in session_list:
        try:
            session.flush()
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    db.session.expunge_all()


def raw_db_connection():
    """Create a raw psycopg2 connection outside the SQLAlchemy pool.

    Use this when you need to change connection-level settings
    (e.g. ISOLATION_LEVEL_AUTOCOMMIT for LISTEN/NOTIFY)
    without contaminating pooled connections.
    """
    url = db.engine.url
    return psycopg2.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
    )
