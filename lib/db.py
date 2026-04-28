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
def no_expire_on_commit(session):
    """Temporarily disable expire_on_commit so ORM objects retain their
    loaded state after commit, avoiding lazy-reload queries.

    Used during MQ batch processing where post_process_rows() needs to
    serialize Host objects into event payloads after the session commits.
    Without this, each attribute access triggers a SELECT per host.

    On exit, expire_all() is called to purge stale objects from the identity
    map. Without this, objects committed while expire_on_commit was False
    would persist across subsequent batches and could return stale data on
    queries that hit the identity map instead of the DB.
    """
    actual_session = session() if callable(session) else session
    original = actual_session.expire_on_commit
    actual_session.expire_on_commit = False
    try:
        yield
    finally:
        actual_session.expire_on_commit = original
        actual_session.expire_all()


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
