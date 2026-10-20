from unittest.mock import Mock

import pytest
from flask import Flask

from app.models.database import RoutingSession
from app.models.database import use_primary_database


@pytest.fixture
def database_engines():
    primary = Mock(name="primary")
    replica = Mock(name="replica")
    app = Flask(__name__)
    app.extensions["inventory_read_engine"] = replica
    return app, primary, replica


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_read_requests_use_replica(database_engines, method):
    app, primary, replica = database_engines
    session = RoutingSession(bind=primary)

    with app.test_request_context("/", method=method):
        assert session.get_bind() is replica


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"])
def test_non_read_requests_use_primary(database_engines, method):
    app, primary, _ = database_engines
    session = RoutingSession(bind=primary)

    with app.test_request_context("/", method=method):
        assert session.get_bind() is primary


def test_workers_use_primary_without_request_context(database_engines):
    app, primary, _ = database_engines
    session = RoutingSession(bind=primary)

    with app.app_context():
        assert session.get_bind() is primary


def test_read_request_can_be_forced_to_primary(database_engines):
    app, primary, _ = database_engines
    session = RoutingSession(bind=primary)

    with app.test_request_context("/", method="GET"):
        use_primary_database()
        assert session.get_bind() is primary
