import os
import time
from hashlib import md5

from alembic import context
from flask import current_app
from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import engine_from_config
from sqlalchemy import inspect
from sqlalchemy import pool
from sqlalchemy.schema import CreateSchema

from app.logging import get_logger

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
logger = get_logger("alembic.env")

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

config.set_main_option("sqlalchemy.url", current_app.config.get("SQLALCHEMY_DATABASE_URI"))
target_metadata = current_app.extensions["migrate"].db.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

schema_name = os.getenv("INVENTORY_DB_SCHEMA", "hbi")

# Migration lock configuration
# Convert a unique string to a numeric lock ID for PostgreSQL advisory locks
# PostgreSQL advisory locks require a bigint (8-byte integer) as the lock ID
MIGRATION_LOCK_ID = int.from_bytes(
    md5(b"insights-host-inventory-migrations").digest()[:8], byteorder="big", signed=True
)
# Maximum time to wait for migration lock (in seconds)
MIGRATION_LOCK_TIMEOUT = int(os.getenv("MIGRATION_LOCK_TIMEOUT", "1800"))  # 30 minutes default
# Retry interval when lock is held by another pod (in seconds)
MIGRATION_LOCK_RETRY_INTERVAL = int(os.getenv("MIGRATION_LOCK_RETRY_INTERVAL", "15"))


def acquire_migration_lock(conn: Connection, timeout: int = MIGRATION_LOCK_TIMEOUT) -> bool:
    """
    Acquire a PostgreSQL advisory lock for running migrations.

    This prevents multiple pods from running migrations simultaneously by using
    PostgreSQL's advisory locking mechanism. The function will retry acquiring
    the lock until the timeout is reached.

    Args:
        conn: SQLAlchemy connection object
        timeout: Maximum time to wait for the lock (in seconds)

    Returns:
        True if lock was acquired, False if timeout was reached
    """
    start_time = time.time()
    attempt = 0

    while True:
        attempt += 1
        elapsed = time.time() - start_time

        # Try to acquire the lock (non-blocking)
        result = conn.execute(f"SELECT pg_try_advisory_lock({MIGRATION_LOCK_ID})").scalar()

        if result:
            logger.info(
                f"Successfully acquired migration lock (ID: {MIGRATION_LOCK_ID}) "
                f"after {attempt} attempt(s) and {elapsed:.1f} seconds"
            )
            return True

        # Check if we've exceeded the timeout
        if elapsed >= timeout:
            logger.error(
                f"Failed to acquire migration lock (ID: {MIGRATION_LOCK_ID}) "
                f"after {timeout} seconds and {attempt} attempts. "
                "Another pod may be running migrations or a previous migration may have hung. "
                "Check for long-running migrations or increase MIGRATION_LOCK_TIMEOUT."
            )
            return False

        # Log waiting status periodically (every 30 seconds)
        if attempt == 1 or (elapsed % 30 < MIGRATION_LOCK_RETRY_INTERVAL):
            logger.info(
                f"Waiting for migration lock (ID: {MIGRATION_LOCK_ID})... "
                f"Attempt {attempt}, elapsed: {elapsed:.1f}s, "
                f"timeout: {timeout}s. Another pod is currently running migrations."
            )

        # Wait before retrying
        time.sleep(MIGRATION_LOCK_RETRY_INTERVAL)


def release_migration_lock(conn: Connection):
    """
    Release the PostgreSQL advisory lock for migrations.

    Args:
        conn: SQLAlchemy connection object
    """
    try:
        result = conn.execute(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})").scalar()

        if result:
            logger.info(f"Successfully released migration lock (ID: {MIGRATION_LOCK_ID})")
        else:
            logger.warning(
                f"Attempted to release migration lock (ID: {MIGRATION_LOCK_ID}) but lock was not held by this session"
            )
    except Exception as e:
        logger.error(f"Error releasing migration lock (ID: {MIGRATION_LOCK_ID}): {e}")


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, version_table_schema=schema_name)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):  # noqa: ARG001, required by alembic
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    def create_schema_if_not_exists(engine: Engine, conn: Connection, schema: str):
        inspection = inspect(engine)
        if not inspection.has_schema(schema):
            conn.execute(CreateSchema(schema))

    def configure_context(conn: Connection, schema: str):
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
            **current_app.extensions["migrate"].configure_args,
            version_table_schema=schema,
        )

    def migrate_alembic_version_table(conn: Connection):
        # Temporarily switch to public schema to get the current revision
        configure_context(conn, "public")
        current_revision = context.get_context().get_current_revision()

        # Configure for the new schema
        configure_context(conn, schema_name)

        # Stamp revision (if available) so that we don't run the migrations from scratch
        if current_revision is not None:
            context.get_context().stamp(context.script, current_revision)
            conn.commit()

    engine = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    connection = engine.connect()
    create_schema_if_not_exists(engine, connection, schema_name)

    # Acquire migration lock BEFORE doing any migration work
    # This ensures only one pod runs migrations at a time
    lock_acquired = acquire_migration_lock(connection)

    if not lock_acquired:
        logger.error(
            "Could not acquire migration lock. Exiting to prevent concurrent migrations. "
            "This pod will not start until migrations are completed by another pod or the lock is released."
        )
        connection.close()
        # Exit with error code to signal failure to container orchestrator
        import sys

        sys.exit(1)

    try:
        # Get current revision
        configure_context(connection, schema_name)
        curr_revision = context.get_context().get_current_revision()

        # If there is no current revision, we need to migrate the version_table
        if curr_revision is None:
            migrate_alembic_version_table(connection)

        # Run migrations within a transaction
        with context.begin_transaction():
            logger.info("Starting database migrations...")
            context.run_migrations()
            logger.info("Database migrations completed successfully")
    finally:
        # Always release the lock, even if migrations fail
        release_migration_lock(connection)
        connection.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
