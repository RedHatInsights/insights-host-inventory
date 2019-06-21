import contextlib
import os
import pytest
import unittest.mock

from app import create_app, db
from app.models import Host


@contextlib.contextmanager
def set_environment(new_env=None):
    new_env = new_env or {}
    patched_dict = unittest.mock.patch.dict(os.environ, new_env)
    patched_dict.start()
    os.environ.clear()
    os.environ.update(new_env)
    yield
    patched_dict.stop()


def rename_host_table_and_indexes():
    """
    Temporarily rename the host table while the tests run.  This is done
    to make dropping the table at the end of the tests a bit safer.
    """
    temp_table_name_suffix = "__unit_tests__"
    if temp_table_name_suffix not in Host.__table__.name:
        Host.__table__.name = Host.__table__.name + temp_table_name_suffix
    if temp_table_name_suffix not in Host.__table__.fullname:
        Host.__table__.fullname = Host.__table__.fullname + temp_table_name_suffix

    # Adjust the names of the indices
    for index in Host.__table_args__:
        if temp_table_name_suffix not in index.name:
            index.name = index.name + temp_table_name_suffix


@pytest.fixture
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
