import io
import json
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from http import HTTPStatus
from unittest import mock
from uuid import uuid4

import pytest
from marshmallow.exceptions import ValidationError
from sqlalchemy.orm.exc import ObjectDeletedError

from api.host_query_db import get_hosts_to_export
from app.auth.identity import Identity
from app.exceptions import InventoryException
from app.queue.export_service import _format_export_data
from app.queue.export_service import _handle_export_error
from app.queue.export_service import _handle_export_response
from app.queue.export_service import _StreamingExportBody
from app.queue.export_service import build_headers
from app.queue.export_service import create_export
from app.queue.export_service_mq import parse_export_service_message
from app.queue.host_mq import OperationResult
from app.serialization import _EXPORT_SERVICE_FIELDS
from app.serialization import serialize_host_for_export_svc
from app.staleness_serialization import get_sys_default_staleness
from tests.helpers import export_service_utils as es_utils
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import mocked_export_post
from tests.helpers.db_utils import db_host
from tests.helpers.test_utils import USER_IDENTITY


@mock.patch("requests.Session.post", autospec=True)
def test_handle_create_export_happy_path(mock_post, db_create_host, flask_app, export_service_consumer_mock):
    with flask_app.app.app_context():
        db_create_host()
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = export_service_consumer_mock.handle_message(export_message)
        assert isinstance(resp, OperationResult)


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
def test_handle_create_export_request_with_data_to_export(mock_post, flask_app, export_service_consumer_mock):
    with (
        flask_app.app.app_context(),
        mock.patch("app.queue.export_service.get_hosts_to_export", return_value=iter(es_utils.EXPORT_DATA)),
        mock.patch("app.queue.export_service.create_export", return_value=True),
    ):
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = export_service_consumer_mock.handle_message(export_message)
        assert isinstance(resp, OperationResult)


@mock.patch("requests.Session.post", autospec=True)
def test_handle_create_export_request_with_no_data_to_export(mock_post, flask_app, export_service_consumer_mock):
    with (
        flask_app.app.app_context(),
        mock.patch("app.queue.export_service.get_hosts_to_export", return_value=iter([])),
        mock.patch("app.queue.export_service.create_export", return_value=False),
    ):
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = export_service_consumer_mock.handle_message(export_message)
        assert resp is None


@pytest.mark.parametrize(
    "field_to_remove", ["id", "source", "subject", "specversion", "type", "time", "redhatorgid", "dataschema", "data"]
)
def test_handle_create_export_missing_field(field_to_remove, flask_app, export_service_consumer_mock):
    with flask_app.app.app_context():
        with pytest.raises(ValidationError):
            export_message = es_utils.create_export_message_missing_field_mock(field_to_remove)
            export_service_consumer_mock.handle_message(export_message)


def test_handle_create_export_wrong_application(flask_app, export_service_consumer_mock):
    with flask_app.app.app_context():
        export_message = es_utils.create_export_message_mock()
        export_message = json.loads(export_message)
        export_message["data"]["resource_request"]["application"] = "foo"
        export_message = json.dumps(export_message)

        resp = export_service_consumer_mock.handle_message(export_message)

        assert resp is None


def test_handle_create_export_empty_message(flask_app, export_service_consumer_mock):
    with flask_app.app.app_context():
        with pytest.raises(ValidationError):
            export_message = ""
            export_message = json.dumps(export_message)

            export_service_consumer_mock.handle_message(export_message)


def test_host_serialization(flask_app, db_create_host):
    with flask_app.app.app_context():
        expected_fields = _EXPORT_SERVICE_FIELDS
        host = db_create_host(host=db_host())
        staleness = get_sys_default_staleness()
        serialized_host = serialize_host_for_export_svc(host, staleness=staleness)

        assert expected_fields == list(serialized_host.keys())


def test_handle_csv_format(flask_app, db_create_host, mocker):
    with flask_app.app.app_context():
        host = db_create_host(host=db_host())
        staleness = get_sys_default_staleness()
        serialized_host = serialize_host_for_export_svc(host, staleness=staleness)
        export_host = _format_export_data([serialized_host], "csv")

        csv_file = io.StringIO(export_host)
        mocker.patch("builtins.open", return_value=csv_file)
        export_host = es_utils.read_csv("mocked.csv")
        mocked_csv = es_utils.create_export_csv_mock(mocker)

        assert mocked_csv == export_host


def test_handle_json_format(flask_app, db_create_host, mocker):
    with flask_app.app.app_context():
        host = db_create_host(host=db_host())
        staleness = get_sys_default_staleness()
        serialized_host = serialize_host_for_export_svc(host, staleness=staleness)

        export_host = json.loads(_format_export_data([serialized_host], "json"))
        mocked_json = es_utils.create_export_json_mock(mocker)
        assert mocked_json == export_host


@pytest.mark.usefixtures("enable_rbac")
@mock.patch("requests.Session.post", autospec=True)
def test_handle_rbac_allowed(mock_post, subtests, flask_app, db_create_host, mocker, export_service_consumer_mock):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            with flask_app.app.app_context():
                get_rbac_permissions_mock.return_value = mock_rbac_response

                db_create_host()
                export_message = es_utils.create_export_message_mock()
                mock_post.return_value.status_code = 202
                resp = export_service_consumer_mock.handle_message(export_message)
                assert isinstance(resp, OperationResult)


@pytest.mark.usefixtures("enable_rbac")
@mock.patch("requests.Session.post", autospec=True)
def test_handle_rbac_prohibited(mock_post, subtests, flask_app, db_create_host, mocker, export_service_consumer_mock):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            with flask_app.app.app_context():
                get_rbac_permissions_mock.return_value = mock_rbac_response

                db_create_host()
                export_message = es_utils.create_export_message_mock()
                mock_post.return_value.status_code = 202
                resp = export_service_consumer_mock.handle_message(export_message)
                assert resp is None


@mock.patch("requests.Session.post", autospec=True)
@mock.patch("app.queue.export_service.resolve_permission", return_value=(True, None))
def test_handle_kessel_allowed(mock_resolve, mock_post, flask_app, db_create_host, export_service_consumer_mock):
    with flask_app.app.app_context():
        db_create_host()
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202

        resp = export_service_consumer_mock.handle_message(export_message)

        assert isinstance(resp, OperationResult)
        mock_resolve.assert_called_once()

        args, kwargs = mock_resolve.call_args
        assert len(args) == 2
        assert isinstance(kwargs["rbac_request_headers"], dict)

        _, permission = args
        assert permission is not None


@mock.patch("requests.Session.post", autospec=True)
@mock.patch("app.queue.export_service.resolve_permission", return_value=(False, None))
def test_handle_kessel_prohibited(mock_resolve, mock_post, flask_app, db_create_host, export_service_consumer_mock):
    with flask_app.app.app_context():
        db_create_host()
        export_message = es_utils.create_export_message_mock()
        mock_post.return_value.status_code = 202
        resp = export_service_consumer_mock.handle_message(export_message)
        assert resp is None
        mock_resolve.assert_called_once()


def test_do_not_export_culled_hosts(flask_app, db_create_host, db_create_staleness_culling, inventory_config):
    with flask_app.app.app_context():
        CUSTOM_STALENESS_DELETE = {
            "conventional_time_to_stale": 1,
            "conventional_time_to_stale_warning": 1,
            "conventional_time_to_delete": 1,
        }

        with mock.patch("app.models.utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime.now(UTC) - timedelta(minutes=1)
            db_create_staleness_culling(**CUSTOM_STALENESS_DELETE)
            db_create_host()

        identity = Identity(USER_IDENTITY)
        host_list = list(
            get_hosts_to_export(identity, rbac_filter=None, batch_size=inventory_config.export_svc_batch_size)
        )

        assert len(host_list) == 0


def test_export_one_host(flask_app, db_create_host, inventory_config):
    with flask_app.app.app_context():
        db_create_host()
        identity = Identity(USER_IDENTITY)
        host_list = list(
            get_hosts_to_export(identity, rbac_filter=None, batch_size=inventory_config.export_svc_batch_size)
        )

        assert len(host_list) == 1


@mock.patch("api.host_query_db.db.session.scalars", side_effect=ObjectDeletedError(None))
def test_export_catches_db_error(flask_app, inventory_config, mocker):
    with flask_app.app.app_context():
        handle_export_error_mock = mocker.patch("app.queue.export_service._handle_export_error")

        validated_msg = parse_export_service_message(es_utils.create_export_message_mock())
        base64_x_rh_identity = validated_msg["data"]["resource_request"]["x_rh_identity"]

        create_export(validated_msg, base64_x_rh_identity, inventory_config)
        handle_export_error_mock.assert_called_once()


def _make_response(status_code, text=""):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestStreamingExportBody:
    def test_json_stream_matches_materialized_format(self):
        hosts = [{"host_id": "1", "display_name": "host-a"}, {"host_id": "2", "display_name": "host-b"}]
        streamed = b"".join(_StreamingExportBody(iter(hosts), "json")).decode("utf-8")
        assert streamed == _format_export_data(hosts, "json")
        assert json.loads(streamed) == hosts

    def test_json_stream_empty_iterator(self):
        hosts = []
        body = _StreamingExportBody(iter(hosts), "json")
        streamed = b"".join(body).decode("utf-8")

        assert streamed == "[]"
        assert body.host_count == 0

    def test_csv_stream_empty_iterator_emits_only_header(self):
        hosts = []
        body = _StreamingExportBody(iter(hosts), "csv")
        streamed = b"".join(body).decode("utf-8")

        assert streamed == _format_export_data(hosts, "csv")
        lines = streamed.splitlines()
        assert len(lines) == 1
        assert body.host_count == 0

    def test_csv_stream_includes_header_and_rows(self):
        hosts = [
            {
                "display_name": "host-a",
                "fqdn": "host-a.example.com",
                "host_id": "1",
                "subscription_manager_id": None,
                "satellite_id": None,
                "group_id": None,
                "group_name": None,
                "os_release": "8.10",
                "updated": "2026-01-01T00:00:00+00:00",
                "state": "fresh",
                "tags": [{"namespace": "insights", "key": "env", "value": "prod"}],
                "host_type": "conventional",
            }
        ]
        body = _StreamingExportBody(iter(hosts), "csv")
        csv_output = b"".join(body).decode("utf-8")
        assert body.host_count == 1
        assert csv_output == _format_export_data(hosts, "csv")
        assert "host-a.example.com" in csv_output


class TestHandleExportResponse:
    def test_accepted_response(self):
        _handle_export_response(_make_response(HTTPStatus.ACCEPTED, "payload delivered"), uuid4(), "json")

    @pytest.mark.parametrize(
        "status_code",
        [HTTPStatus.BAD_REQUEST, HTTPStatus.CONFLICT, HTTPStatus.INTERNAL_SERVER_ERROR],
    )
    def test_already_processed_does_not_raise(self, status_code):
        resp = _make_response(
            status_code,
            '{"detail": "this resource has already been processed", "status": 400}',
        )
        _handle_export_response(resp, uuid4(), "csv")

    def test_other_400_still_raises(self):
        resp = _make_response(HTTPStatus.BAD_REQUEST, '{"detail": "some other error"}')
        with pytest.raises(InventoryException):
            _handle_export_response(resp, uuid4(), "json")

    def test_server_error_raises(self):
        resp = _make_response(HTTPStatus.INTERNAL_SERVER_ERROR, "internal error")
        with pytest.raises(InventoryException):
            _handle_export_response(resp, uuid4(), "json")


class TestHandleExportError:
    def test_error_handler_does_not_propagate_post_failure(self):
        session = mock.Mock()
        session.post.side_effect = ConnectionError("network down")
        _handle_export_error("some error", 500, "http://example.com/error", session, {}, uuid4(), "json")

    def test_error_handler_does_not_propagate_response_error(self):
        session = mock.Mock()
        session.post.return_value = _make_response(HTTPStatus.INTERNAL_SERVER_ERROR, "boom")
        _handle_export_error("some error", 500, "http://example.com/error", session, {}, uuid4(), "json")

    def test_error_handler_succeeds_normally(self):
        session = mock.Mock()
        session.post.return_value = _make_response(HTTPStatus.ACCEPTED)
        _handle_export_error("some error", 500, "http://example.com/error", session, {}, uuid4(), "json")
        session.post.assert_called_once()


@mock.patch("requests.Session.post", autospec=True)
def test_create_export_posts_streaming_body(mock_post, db_create_host, flask_app, inventory_config):
    """create_export must pass a _StreamingExportBody to session.post, not a pre-materialized str/bytes."""
    with flask_app.app.app_context():
        db_create_host()

        mock_post.return_value.status_code = HTTPStatus.ACCEPTED
        mock_post.return_value.text = ""

        validated_msg = parse_export_service_message(es_utils.create_export_message_mock())
        base64_x_rh_identity = validated_msg["data"]["resource_request"]["x_rh_identity"]

        create_export(validated_msg, base64_x_rh_identity, inventory_config)

        upload_call = mock_post.call_args_list[-1]
        data_arg = upload_call.kwargs.get("data") or upload_call[1].get("data")
        assert isinstance(data_arg, _StreamingExportBody), f"Expected _StreamingExportBody, got {type(data_arg)}"


@mock.patch("requests.Session.post", autospec=True)
def test_create_export_already_processed_returns_true(mock_post, db_create_host, flask_app, inventory_config):
    """When the upload gets 'already processed', create_export should return True (not raise)."""
    with flask_app.app.app_context():
        db_create_host()

        mock_post.return_value.status_code = HTTPStatus.BAD_REQUEST
        mock_post.return_value.text = (
            '{"detail": "this resource has already been processed", "status": 400, "title": null}'
        )

        validated_msg = parse_export_service_message(es_utils.create_export_message_mock())
        base64_x_rh_identity = validated_msg["data"]["resource_request"]["x_rh_identity"]

        result = create_export(validated_msg, base64_x_rh_identity, inventory_config)
        assert result is True


class TestBuildHeaders:
    """Auth selection for export-service based on the V2 `authenticated` field."""

    def test_unauthenticated_endpoint_uses_psk(self, inventory_config):
        inventory_config.export_service_endpoint_authenticated = False
        inventory_config.export_service_token = "test-psk"

        _, request_headers = build_headers("dummy-identity", uuid4(), inventory_config, "json")

        assert request_headers["x-rh-exports-psk"] == "test-psk"
        assert "Authorization" not in request_headers

    def test_authenticated_endpoint_uses_kessel_token(self, inventory_config, mocker):
        inventory_config.export_service_endpoint_authenticated = True
        mocker.patch(
            "app.queue.export_service._get_export_service_access_token",
            return_value="kessel-token-xyz",
        )

        _, request_headers = build_headers("dummy-identity", uuid4(), inventory_config, "json")

        assert request_headers["Authorization"] == "Bearer kessel-token-xyz"
        assert "x-rh-exports-psk" not in request_headers


@mock.patch("requests.Session.post", autospec=True)
def test_create_export_honors_ca_certificate(mock_post, db_create_host, flask_app, inventory_config):
    """create_export must set session.verify from the V2 endpoint CA certificate."""
    with flask_app.app.app_context():
        db_create_host()

        inventory_config.export_service_endpoint_ca_certificate = "/path/to/ca.crt"
        mock_post.return_value.status_code = HTTPStatus.ACCEPTED
        mock_post.return_value.text = ""

        validated_msg = parse_export_service_message(es_utils.create_export_message_mock())
        base64_x_rh_identity = validated_msg["data"]["resource_request"]["x_rh_identity"]

        create_export(validated_msg, base64_x_rh_identity, inventory_config)

        # The Session instance is the first positional arg (autospec=True) of the post call.
        session_instance = mock_post.call_args_list[-1][0][0]
        assert session_instance.verify == "/path/to/ca.crt"
