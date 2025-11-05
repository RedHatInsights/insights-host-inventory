from contextlib import contextmanager

from app.models import db


@contextmanager
def session_guard(session):
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def multi_session_guard(session_list):
    yield session_list
    for session in session_list:
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    db.session.expunge_all()
