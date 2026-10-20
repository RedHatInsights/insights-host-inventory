from unittest.mock import Mock
from unittest.mock import patch

import pytest
from flask import Flask
from flask_sqlalchemy.session import Session as FlaskSession
from sqlalchemy.exc import DBAPIError

from app.models.database import RoutingSession
from app.models.database import use_primary_database


@pytest.fixture
def database_engines():
    primary = Mock(name="primary")
    replica = Mock(name="replica")
    app = Flask(__name__)
    app.extensions["inventory_read_engine"] = replica
    # Flask-SQLAlchemy selects the primary engine from db.engines[None].
    database = Mock()
    database.engines = {None: primary}
    session = RoutingSession(database)
    return app, session, primary, replica


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_read_requests_use_replica(database_engines, method):
    app, session, _, replica = database_engines

    with app.test_request_context("/", method=method):
        assert session.get_bind() is replica


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"])
def test_non_read_requests_use_primary(database_engines, method):
    app, session, primary, _ = database_engines

    with app.test_request_context("/", method=method):
        assert session.get_bind() is primary


def test_workers_use_primary_without_request_context(database_engines):
    app, session, primary, _ = database_engines

    with app.app_context():
        assert session.get_bind() is primary


def test_read_request_can_be_forced_to_primary(database_engines):
    app, session, primary, _ = database_engines

    with app.test_request_context("/", method="GET"):
        use_primary_database()
        assert session.get_bind() is primary


def test_replica_error_retries_read_on_primary(database_engines):
    app, primary, _ = database_engines
    session = RoutingSession(bind=primary)
    replica_error = DBAPIError("SELECT", {}, RuntimeError("replica unavailable"))

    with app.test_request_context("/", method="GET"):
        with patch.object(FlaskSession, "execute", side_effect=[replica_error, "result"]):
            with patch.object(RoutingSession, "rollback") as rollback:
                assert session.execute("SELECT 1") == "result"

        rollback.assert_called_once_with()
        assert session.get_bind() is primary
