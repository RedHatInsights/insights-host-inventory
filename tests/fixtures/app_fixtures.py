import pytest
from sqlalchemy import text as sa_text

from app import create_app
from app import db
from app.config import Config
from app.config import RuntimeEnvironment
from tests.helpers.db_utils import clean_tables


@pytest.fixture(scope="session")
def new_flask_app(database):
    application = create_app(RuntimeEnvironment.TEST)
    with application.app.app_context():
        db.session.execute(sa_text("CREATE SCHEMA IF NOT EXISTS hbi"))
        db.session.commit()
        db.create_all()

        yield application

        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def flask_app(new_flask_app):
    yield new_flask_app

    clean_tables()


@pytest.fixture(scope="function")
def inventory_config(flask_app):
    yield flask_app.app.config["INVENTORY_CONFIG"]
    flask_app.app.config["INVENTORY_CONFIG"] = Config(RuntimeEnvironment.TEST)
