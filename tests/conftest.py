from pytest import fixture

from app import create_app
from app import db
from .test_utils import rename_host_table_and_indexes


@fixture
def flask_app_fixture():
    rename_host_table_and_indexes()

    app = create_app(config_name="testing")

    # binds the app to the current context
    with app.app_context() as ctx:
        # create all tables
        db.create_all()
        ctx.push()
        yield app
        ctx.pop

        db.session.remove()
        db.drop_all()
