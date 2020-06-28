import os
import sys

import pytest
from sqlalchemy_utils import create_database
from sqlalchemy_utils import database_exists
from sqlalchemy_utils import drop_database

from app import create_app
from app import db
from app.config import Config
from app.config import RuntimeEnvironment
from tests.helpers.db_utils import clean_tables

# Make test helpers available to be imported
sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))


@pytest.fixture(scope="session")
def database():
    config = Config(RuntimeEnvironment.TEST)
    # if not database_exists(config.db_uri):
    #     create_database(config.db_uri)

    yield config.db_uri

    # drop_database(config.db_uri)


@pytest.fixture(scope="session")
def new_flask_app(database):
    app = create_app(RuntimeEnvironment.TEST)
    app.testing = True

    with app.app_context() as ctx:
        db.create_all()
        ctx.push()

        yield app

        ctx.pop()
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def flask_app(new_flask_app):
    with new_flask_app.app_context():
        yield new_flask_app

        clean_tables()


pytest_plugins = ["tests.fixtures.api_fixtures", "tests.fixtures.db_fixtures", "tests.fixtures.mq_fixtures"]
