from contextlib import contextmanager

from app.models import db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import Config

# TODO: This is a temporary solution to create a separate database session for independent database operations.
@contextmanager
def get_independent_db_session():
    """Create a separate database session for independent database operations."""
    # Create a new engine and session factory
    engine = create_engine(Config.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


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
