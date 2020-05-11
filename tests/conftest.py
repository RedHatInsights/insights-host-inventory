import pytest
from sqlalchemy_utils import create_database
from sqlalchemy_utils import database_exists
from sqlalchemy_utils import drop_database

from app import create_app
from app import db
from app.config import RuntimeEnvironment
from app.config import TestConfig


@pytest.fixture(scope="session")
def database_fixture():
    config = TestConfig(RuntimeEnvironment.server)
    if not database_exists(config.db_uri):
        create_database(config.db_uri)

    yield config.db_uri

    drop_database(config.db_uri)


@pytest.fixture(scope="function")
def flask_app_fixture(database_fixture):
    app = create_app(config_name="testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_fixture

    # binds the app to the current context
    with app.app_context() as ctx:
        db.create_all()
        ctx.push()

        yield app

        ctx.pop()
        db.session.remove()
        db.drop_all()
