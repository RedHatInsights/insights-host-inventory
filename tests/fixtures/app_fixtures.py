# mypy: disallow-untyped-defs

from collections.abc import Generator

import pytest
from connexion import FlaskApp
from sqlalchemy import text as sa_text

from app import create_app
from app.config import Config
from app.environment import RuntimeEnvironment
from app.models import db
from tests.helpers.db_utils import clean_tables


@pytest.fixture(scope="session")
def new_flask_app(database: str) -> Generator[FlaskApp]:  # noqa: ARG001
    application = create_app(RuntimeEnvironment.TEST)
    with application.app.app_context():
        db.session.execute(sa_text("CREATE SCHEMA IF NOT EXISTS hbi"))
        db.session.commit()
        db.create_all()

        yield application

        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def flask_app(new_flask_app: FlaskApp) -> Generator[FlaskApp]:
    yield new_flask_app

    clean_tables()


@pytest.fixture(scope="function")
def inventory_config(flask_app: FlaskApp) -> Generator[Config]:
    yield flask_app.app.config["INVENTORY_CONFIG"]
    flask_app.app.config["INVENTORY_CONFIG"] = Config(RuntimeEnvironment.TEST)


@pytest.fixture(scope="function")
def no_dry_run_config(inventory_config: Config) -> Config:
    inventory_config.dry_run = False
    return inventory_config


@pytest.fixture(scope="function")
def require_logical_replication(flask_app: FlaskApp) -> None:
    """Fixture that skips the test if logical replication is not enabled.

    This fixture checks if PostgreSQL has wal_level set to 'logical' and skips
    the test if it's not enabled. This is useful for tests that require logical
    replication features like replication slots.

    Args:
        flask_app: Flask application fixture (required dependency)

    Raises:
        pytest.skip: If logical replication is not enabled
    """
    with flask_app.app.app_context():
        try:
            result = db.session.execute(sa_text("SHOW wal_level")).scalar()
            if result != "logical":
                pytest.skip("Logical replication not enabled (wal_level != 'logical')")
        except Exception:
            pytest.skip("Could not check logical replication status")
