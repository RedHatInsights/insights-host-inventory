from contextlib import contextmanager

from alembic import op
from sqlalchemy.orm.session import Session

from app.logging import get_logger

__all__ = ("logger", "session")


def logger(name):
    return get_logger(f"migrations.{name}")


@contextmanager
def session():
    bind = op.get_bind()
    session = Session(bind)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    else:
        session.commit()
