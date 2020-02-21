from contextlib import contextmanager

from alembic import op
from sqlalchemy.orm.session import Session


__all__ = ("session",)


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
