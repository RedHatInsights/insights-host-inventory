import os
from contextlib import contextmanager

from alembic import op
from sqlalchemy.orm.session import Session

from app.logging import get_logger

__all__ = (
    "logger",
    "session",
    "validate_num_partitions",
    "include_object",
    "TABLE_NUM_PARTITIONS",
    "MIGRATION_MODE",
)


TABLE_NUM_PARTITIONS = int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 1))
MIGRATION_MODE = os.getenv("MIGRATION_MODE", "automated")
INVENTORY_DB_SCHEMA = os.getenv("INVENTORY_DB_SCHEMA", "hbi")


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


def include_object(object, name, type_, reflected, compare_to):  # noqa: ARG001, required by alembic
    """Filter Alembic autogenerate to only include objects in the target schema.

    This prevents Alembic from:
    - Trying to create/drop tables in other schemas (e.g., public)
    - Trying to drop partition tables (e.g., hosts_p0, hosts_p1)
    - Trying to drop backup/old tables (e.g., hosts_old)
    - Trying to drop tables not defined in models (e.g., debezium_signal)
    - Trying to drop columns, indexes, or constraints that exist in DB but not in models

    The key insight is that `reflected=True` and `compare_to=None` means the object
    exists in the database but NOT in the models. We don't want to generate DROP
    statements for such objects, as they may be intentionally present (e.g., for
    production performance, partition management, etc.).
    """
    if type_ == "table":
        # For tables, only include those in the target schema (hbi)
        table_schema = getattr(object, "schema", None)
        if table_schema != INVENTORY_DB_SCHEMA:
            return False

        # If this is a reflected table (from DB) not in our models, exclude it
        # This handles partition tables (_p0, _p1), old tables (_old), and
        # other tables like debezium_signal that exist in DB but not in models
        return not (reflected and compare_to is None)

    # For columns, indexes, unique_constraints, foreign_keys, etc.:
    # If the object exists in DB but not in models, don't try to drop it
    return not (reflected and compare_to is None)
