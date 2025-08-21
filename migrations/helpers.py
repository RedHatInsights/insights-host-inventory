import os
from contextlib import contextmanager

from alembic import op
from sqlalchemy.orm.session import Session

from app.logging import get_logger

__all__ = ("logger", "session", "validate_num_partitions", "TABLE_NUM_PARTITIONS", "MIGRATION_MODE")


TABLE_NUM_PARTITIONS = int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 1))
MIGRATION_MODE = os.getenv("MIGRATION_MODE", "automated")


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


def validate_num_partitions(num_partitions: int):
    if not 1 <= num_partitions <= 32:
        raise ValueError(f"Invalid number of partitions: {num_partitions}. Must be between 1 and 32.")
