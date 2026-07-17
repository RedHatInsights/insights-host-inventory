import json
from http import HTTPStatus
from uuid import UUID

import pytest

from app.models import Host
from app.models import db
from app.queue.events import EventType
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host

ADMIN_HOSTS_URL = "/_admin/hosts"


@pytest.fixture
def enable_admin_hosts(inventory_config):
    inventory_config.admin_hosts_endpoint_enabled = True
    return inventory_config


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_admin_hosts_disabled_by_default(flask_client, inventory_config):
    inventory_config.admin_hosts_endpoint_enabled = False
    host = minimal_host().data()

    response = flask_client.post(ADMIN_HOSTS_URL, json=host)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Host.query.count() == 0


@pytest.mark.usefixtures("enable_admin_hosts", "event_producer_mock", "notification_event_producer_mock")
def test_admin_hosts_create_returns_id(flask_client, event_producer_mock):
    host = minimal_host().data()

    response = flask_client.post(ADMIN_HOSTS_URL, json=host)

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert "id" in body
    created = db.session.get(Host, (UUID(body["id"]), host["org_id"]))
    assert created is not None
    assert created.subscription_manager_id == host["subscription_manager_id"]

    event = json.loads(event_producer_mock.event)
    assert event["type"] == EventType.created.name
    assert event["host"]["id"] == body["id"]


@pytest.mark.usefixtures("enable_admin_hosts", "event_producer_mock", "notification_event_producer_mock")
def test_admin_hosts_update_by_id(flask_client, event_producer_mock):
    host = minimal_host().data()
    create_response = flask_client.post(ADMIN_HOSTS_URL, json=host)
    host_id = create_response.json()["id"]

    updated_display_name = "admin-updated-host"
    host["id"] = host_id
    host["display_name"] = updated_display_name

    update_response = flask_client.post(ADMIN_HOSTS_URL, json=host)

    assert update_response.status_code == HTTPStatus.OK
    assert update_response.json()["id"] == host_id

    updated = db.session.get(Host, (UUID(host_id), host["org_id"]))
    assert updated.display_name == updated_display_name

    event = json.loads(event_producer_mock.event)
    assert event["type"] == EventType.updated.name
    assert event["host"]["id"] == host_id


@pytest.mark.usefixtures("enable_admin_hosts", "event_producer_mock", "notification_event_producer_mock")
def test_admin_hosts_update_missing_host_returns_404(flask_client):
    host = minimal_host(id=generate_uuid()).data()

    response = flask_client.post(ADMIN_HOSTS_URL, json=host)

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.usefixtures("enable_admin_hosts", "event_producer_mock", "notification_event_producer_mock")
def test_admin_hosts_invalid_json_returns_400(flask_client):
    response = flask_client.post(
        ADMIN_HOSTS_URL,
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.usefixtures("enable_admin_hosts", "event_producer_mock", "notification_event_producer_mock")
def test_admin_hosts_missing_org_id_returns_400(flask_client):
    host = minimal_host().data()
    del host["org_id"]

    response = flask_client.post(ADMIN_HOSTS_URL, json=host)

    assert response.status_code == HTTPStatus.BAD_REQUEST
