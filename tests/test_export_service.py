import io
import json
from datetime import datetime
from datetime import timedelta
from unittest import mock

import pytest
from marshmallow.exceptions import ValidationError

from api.staleness_query import get_sys_default_staleness
from app.auth.identity import Identity
from app.culling import Timestamps
from app.culling import _Config as CullingConfig
from app.queue.export_service import _format_export_data
from app.queue.export_service import create_export
from app.queue.export_service import get_host_list
from app.queue.export_service_mq import handle_export_message
from app.queue.export_service_mq import parse_export_service_message
from app.serialization import _EXPORT_SERVICE_FIELDS
from app.serialization import serialize_host_for_export_svc
from tests.helpers import export_service_utils as es_utils
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import mocked_export_post
from tests.helpers.db_utils import db_host
from tests.helpers.test_utils import USER_IDENTITY


@mock.patch("requests.Session.post", autospec=True)
def test_handle_create_export_happy_path(mock_post, db_create_host, flask_app, inventory_config):
    with flask_app.app.app_context():
        db_create_host()
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = handle_export_message(message=export_message, inventory_config=inventory_config)
        assert resp is True


@pytest.mark.parametrize("format", ("json", "csv"))
@mock.patch("requests.Session.post", new=mocked_export_post)
def test_handle_create_export_unicode(db_create_host, flask_app, inventory_config, format):
    with flask_app.app.app_context():
        host_to_create = db_host()
        host_to_create.display_name = "“quotetest”"
        db_create_host(host=host_to_create)

        validated_msg = parse_export_service_message(es_utils.create_export_message_mock(format=format))
        base64_x_rh_identity = validated_msg["data"]["resource_request"]["x_rh_identity"]

        assert create_export(validated_msg, base64_x_rh_identity, inventory_config)


@mock.patch("requests.Session.post", autospec=True)
@mock.patch("app.queue.export_service.get_hosts_to_export", return_value=iter(es_utils.EXPORT_DATA))
@mock.patch("app.queue.export_service.create_export", return_value=True)
def test_handle_create_export_request_with_data_to_export(
    mock_export, mock_rbac, mock_post, flask_app, inventory_config
):
    with flask_app.app.app_context():
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = handle_export_message(message=export_message, inventory_config=inventory_config)
        assert resp is True


@mock.patch("requests.Session.post", autospec=True)
@mock.patch("app.queue.export_service.get_hosts_to_export", return_value=[])
@mock.patch("app.queue.export_service.create_export", return_value=False)
def test_handle_create_export_request_with_no_data_to_export(
    mock_export, mock_rbac, mock_post, flask_app, inventory_config
):
    with flask_app.app.app_context():
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = handle_export_message(message=export_message, inventory_config=inventory_config)
        assert resp is False


@pytest.mark.parametrize(
    "field_to_remove", ["id", "source", "subject", "specversion", "type", "time", "redhatorgid", "dataschema", "data"]
)
def test_handle_create_export_missing_field(field_to_remove, flask_app, inventory_config):
    with flask_app.app.app_context():
        with pytest.raises(ValidationError):
            export_message = es_utils.create_export_message_missing_field_mock(field_to_remove)
            handle_export_message(message=export_message, inventory_config=inventory_config)


def test_handle_create_export_wrong_application(flask_app, inventory_config):
    with flask_app.app.app_context():
        export_message = es_utils.create_export_message_mock()
        export_message = json.loads(export_message)
        export_message["data"]["resource_request"]["application"] = "foo"
        export_message = json.dumps(export_message)

        resp = handle_export_message(message=export_message, inventory_config=inventory_config)

        assert resp is False


def test_handle_create_export_empty_message(flask_app, inventory_config):
    with flask_app.app.app_context():
        with pytest.raises(ValidationError):
            export_message = ""
            export_message = json.dumps(export_message)

            handle_export_message(message=export_message, inventory_config=inventory_config)


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


@pytest.mark.usefixtures("enable_rbac")
@mock.patch("requests.Session.post", autospec=True)
def test_handle_rbac_allowed(mock_post, subtests, flask_app, db_create_host, mocker, inventory_config):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            with flask_app.app.app_context():
                get_rbac_permissions_mock.return_value = mock_rbac_response

                db_create_host()
                export_message = es_utils.create_export_message_mock()
                mock_post.return_value.status_code = 202
                resp = handle_export_message(message=export_message, inventory_config=inventory_config)
                assert resp is True


@pytest.mark.usefixtures("enable_rbac")
@mock.patch("requests.Session.post", autospec=True)
def test_handle_rbac_prohibited(mock_post, subtests, flask_app, db_create_host, mocker, inventory_config):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            with flask_app.app.app_context():
                get_rbac_permissions_mock.return_value = mock_rbac_response

                db_create_host()
                export_message = es_utils.create_export_message_mock()
                mock_post.return_value.status_code = 202
                resp = handle_export_message(message=export_message, inventory_config=inventory_config)
                assert resp is False


def test_do_not_export_culled_hosts(flask_app, db_create_host, db_create_staleness_culling, inventory_config):
    with flask_app.app.app_context():
        CUSTOM_STALENESS_DELETE_CONVENTIONAL_IMMUTABLE = {
            "conventional_time_to_stale": 1,
            "conventional_time_to_stale_warning": 1,
            "conventional_time_to_delete": 1,
            "immutable_time_to_stale": 1,
            "immutable_time_to_stale_warning": 1,
            "immutable_time_to_delete": 1,
        }

        with mock.patch("app.models.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime.now() - timedelta(minutes=1)
            db_create_staleness_culling(**CUSTOM_STALENESS_DELETE_CONVENTIONAL_IMMUTABLE)
            db_create_host()

        identity = Identity(USER_IDENTITY)
        host_list = get_host_list(identity=identity, rbac_filter=None, inventory_config=inventory_config)

        assert len(host_list) == 0


def test_export_one_host(flask_app, db_create_host, inventory_config):
    with flask_app.app.app_context():
        db_create_host()
        identity = Identity(USER_IDENTITY)
        host_list = get_host_list(identity=identity, rbac_filter=None, inventory_config=inventory_config)

        assert len(host_list) == 1
