import os

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
    def process_revision_directives(context, revision, directives):
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

    engine = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    connection = engine.connect()
    create_schema_if_not_exists(engine, connection, schema_name)

    # Get current revision
    configure_context(connection, schema_name)
    curr_revision = context.get_context().get_current_revision()

    # If there is no current revision, we need to migrate the version_table
    if curr_revision is None:
        migrate_alembic_version_table(connection)

    try:
        with context.begin_transaction():
            # Lock so multiple pods don't run the same migration simultaneously
            context.execute("select pg_advisory_lock(1);")
            context.run_migrations()
    finally:
        # Release the lock
        context.execute("select pg_advisory_unlock(1);")
        connection.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
