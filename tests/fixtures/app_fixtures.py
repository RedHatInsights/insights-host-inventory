import pytest
from flask import g

from app import create_app
from app import db
from app.config import Config
from app.config import RuntimeEnvironment
from tests.helpers.db_utils import clean_tables


@pytest.fixture(scope="session")
def new_flask_app(database):
    app = create_app(RuntimeEnvironment.TEST)

    with app.app_context():
        db.create_all()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def flask_app(new_flask_app):
    yield new_flask_app

    clean_tables()


@pytest.fixture(scope="function")
def inventory_config(flask_app):
    yield flask_app.config["INVENTORY_CONFIG"]
    flask_app.config["INVENTORY_CONFIG"] = Config(RuntimeEnvironment.TEST)


@pytest.fixture(scope="function")
def clean_g():
    """
    This value is always set when lib.host_repository.get_staleness_obj is called
    or when a new host is added/updated in MQ.

    This fixture needs to be user on every test that uses a custom staleness.
    """
    if "acc_st" in g:
        del g.acc_st
