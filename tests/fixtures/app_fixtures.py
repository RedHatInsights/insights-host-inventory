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
