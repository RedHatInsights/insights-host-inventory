import io
import json
from datetime import timedelta
from unittest import mock

import pytest
from marshmallow.exceptions import ValidationError

from api.staleness_query import get_sys_default_staleness
from app.culling import _Config as CullingConfig
from app.culling import Timestamps
from app.queue.export_service import _format_export_data
from app.queue.queue import handle_export_message
from app.serialization import _EXPORT_SERVICE_FIELDS
from app.serialization import serialize_host_for_export_svc
from tests.helpers import export_service_utils as es_utils
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.db_utils import db_host


@mock.patch("requests.Session.post", autospec=True)
def test_handle_create_export_happy_path(mock_post, db_create_host, flask_app):
    with flask_app.app.app_context():
        db_create_host()
        config = flask_app.app.config.get("INVENTORY_CONFIG")
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = handle_export_message(message=export_message, inventory_config=config)
        assert resp is True


@mock.patch("requests.Session.post", autospec=True)
@mock.patch("app.queue.export_service.get_hosts_to_export", return_value=iter(es_utils.EXPORT_DATA))
@mock.patch("app.queue.export_service.create_export", return_value=True)
def test_handle_create_export_request_with_data_to_export(mock_export, mock_rbac, mock_post, flask_app):
    with flask_app.app.app_context():
        config = flask_app.app.config.get("INVENTORY_CONFIG")
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = handle_export_message(message=export_message, inventory_config=config)
        assert resp is True


@mock.patch("requests.Session.post", autospec=True)
@mock.patch("app.queue.export_service.get_hosts_to_export", return_value=[])
@mock.patch("app.queue.export_service.create_export", return_value=False)
def test_handle_create_export_request_with_no_data_to_export(mock_export, mock_rbac, mock_post, flask_app):
    with flask_app.app.app_context():
        config = flask_app.app.config.get("INVENTORY_CONFIG")
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = handle_export_message(message=export_message, inventory_config=config)
        assert resp is False


@pytest.mark.parametrize(
    "field_to_remove", ["id", "source", "subject", "specversion", "type", "time", "redhatorgid", "dataschema", "data"]
)
def test_handle_create_export_missing_field(field_to_remove, flask_app):
    with flask_app.app.app_context():
        config = flask_app.app.config.get("INVENTORY_CONFIG")
        with pytest.raises(ValidationError):
            export_message = es_utils.create_export_message_missing_field_mock(field_to_remove)
            handle_export_message(message=export_message, inventory_config=config)


def test_handle_create_export_wrong_application(flask_app):
    with flask_app.app.app_context():
        config = flask_app.app.config.get("INVENTORY_CONFIG")
        export_message = es_utils.create_export_message_mock()
        export_message = json.loads(export_message)
        export_message["data"]["resource_request"]["application"] = "foo"
        export_message = json.dumps(export_message)

        resp = handle_export_message(message=export_message, inventory_config=config)

        assert resp is False


def test_handle_create_export_empty_message(flask_app):
    with flask_app.app.app_context():
        config = flask_app.app.config.get("INVENTORY_CONFIG")
        with pytest.raises(ValidationError):
            export_message = ""
            export_message = json.dumps(export_message)

            handle_export_message(message=export_message, inventory_config=config)


def test_host_serialization(flask_app, db_create_host):
    with flask_app.app.app_context():
        expected_fields = _EXPORT_SERVICE_FIELDS
        host = db_create_host(host=db_host())
        config = CullingConfig(stale_warning_offset_delta=timedelta(days=7), culled_offset_delta=timedelta(days=14))
        staleness_timestamps = Timestamps(config)
        staleness = get_sys_default_staleness()
        serialized_host = serialize_host_for_export_svc(
            host, staleness_timestamps=staleness_timestamps, staleness=staleness
        )

        assert expected_fields == list(serialized_host.keys())


def test_handle_csv_format(flask_app, db_create_host, mocker):
    with flask_app.app.app_context():
        host = db_create_host(host=db_host())
        config = CullingConfig(stale_warning_offset_delta=timedelta(days=7), culled_offset_delta=timedelta(days=14))
        staleness_timestamps = Timestamps(config)
        staleness = get_sys_default_staleness()
        serialized_host = serialize_host_for_export_svc(
            host, staleness_timestamps=staleness_timestamps, staleness=staleness
        )
        export_host = _format_export_data([serialized_host], "csv")

        csv_file = io.StringIO(export_host)
        mocker.patch("builtins.open", return_value=csv_file)
        export_host = es_utils.read_csv("mocked.csv")
        mocked_csv = es_utils.create_export_csv_mock(mocker)

        assert mocked_csv == export_host


def test_handle_json_format(flask_app, db_create_host, mocker):
    with flask_app.app.app_context():
        host = db_create_host(host=db_host())
        config = CullingConfig(stale_warning_offset_delta=timedelta(days=7), culled_offset_delta=timedelta(days=14))
        staleness_timestamps = Timestamps(config)
        staleness = get_sys_default_staleness()
        serialized_host = serialize_host_for_export_svc(
            host, staleness_timestamps=staleness_timestamps, staleness=staleness
        )

        export_host = json.loads(_format_export_data([serialized_host], "json"))
        mocked_json = es_utils.create_export_json_mock(mocker)
        assert mocked_json == export_host


@mock.patch("requests.Session.post", autospec=True)
def test_handle_rbac_allowed(mock_post, subtests, flask_app, db_create_host, mocker, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            with flask_app.app.app_context():
                get_rbac_permissions_mock.return_value = mock_rbac_response

                db_create_host()
                config = flask_app.app.config.get("INVENTORY_CONFIG")
                export_message = es_utils.create_export_message_mock()
                mock_post.return_value.status_code = 202
                resp = handle_export_message(message=export_message, inventory_config=config)
                assert resp is True


@mock.patch("requests.Session.post", autospec=True)
def test_handle_rbac_prohibited(mock_post, subtests, flask_app, db_create_host, mocker, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            with flask_app.app.app_context():
                get_rbac_permissions_mock.return_value = mock_rbac_response

                db_create_host()
                config = flask_app.app.config.get("INVENTORY_CONFIG")
                export_message = es_utils.create_export_message_mock()
                mock_post.return_value.status_code = 202
                resp = handle_export_message(message=export_message, inventory_config=config)
                assert resp is False
