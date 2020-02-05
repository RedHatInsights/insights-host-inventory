from contextlib import contextmanager


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
