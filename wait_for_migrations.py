#!/usr/bin/env python3
"""
Wait for database migrations to complete.

This script polls the alembic_version table until it matches the expected
head revision from the migration scripts. Used as an init container to ensure
migrations are complete before the main application starts.
"""

import os
import sys
import time

from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import ProgrammingError

from app.config import Config as AppConfig
from app.environment import RuntimeEnvironment
from app.logging import get_logger

LOGGER_NAME = "wait-for-migrations"
POLL_INTERVAL_SECONDS = int(os.getenv("WAIT_FOR_MIGRATIONS_POLL_INTERVAL_SECONDS", "5"))
MAX_WAIT_SECONDS = int(os.getenv("WAIT_FOR_MIGRATIONS_TIMEOUT_SECONDS", "300"))


def get_head_revision() -> str:
    """Get the expected head revision from alembic migration scripts."""
    script_dir = ScriptDirectory("migrations")
    return script_dir.get_current_head()


def get_current_db_revision(engine, schema: str) -> str | None:
    """Query the current revision from the database's alembic_version table."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT version_num FROM {schema}.alembic_version"))
            row = result.fetchone()
            return row[0] if row else None
    except (OperationalError, ProgrammingError):
        # Table doesn't exist yet or connection failed
        return None


def wait_for_migrations(logger) -> bool:
    """
    Wait until database migrations are complete.

    Returns True if migrations completed successfully, False if timed out.
    """
    config = AppConfig(RuntimeEnvironment.SERVICE)
    engine = create_engine(config.db_uri)
    schema = os.getenv("INVENTORY_DB_SCHEMA", "hbi")

    head_revision = get_head_revision()
    logger.info(f"Expected head revision: {head_revision}")

    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        if elapsed > MAX_WAIT_SECONDS:
            logger.error(f"Timed out after {MAX_WAIT_SECONDS}s waiting for migrations")
            engine.dispose()
            return False

        current_revision = get_current_db_revision(engine, schema)

        if current_revision == head_revision:
            logger.info(f"Migrations complete! Current revision: {current_revision}")
            engine.dispose()
            return True

        logger.info(
            f"Waiting for migrations... current={current_revision}, expected={head_revision} "
            f"(elapsed: {int(elapsed)}s)"
        )
        time.sleep(POLL_INTERVAL_SECONDS)


def main():
    logger = get_logger(LOGGER_NAME)
    logger.info("Starting migration wait...")

    success = wait_for_migrations(logger)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
