import io
import json
import logging
from contextlib import contextmanager
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from http import HTTPStatus
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import pytest
from marshmallow.exceptions import ValidationError
from requests import Response
from sqlalchemy import event
from sqlalchemy.orm.exc import ObjectDeletedError

from api.host_query_db import _export_needs_profile_joins
from api.host_query_db import get_hosts_to_export
from app.auth.identity import Identity
from app.exceptions import InventoryException
from app.logging import ContextualFilter
from app.logging import threadctx
from app.models import db
from app.queue.export_service import _build_export_request_url
from app.queue.export_service import _format_compliance_policies
from app.queue.export_service import _format_export_data
from app.queue.export_service import _handle_export_error
from app.queue.export_service import _handle_export_response
from app.queue.export_service import _load_view_config
from app.queue.export_service import _StreamingExportBody
from app.queue.export_service import build_headers
from app.queue.export_service import create_export
from app.queue.export_service import resolve_export_columns
from app.queue.export_service_mq import parse_export_service_message
from app.queue.host_mq import OperationResult
from app.serialization import _EXPORT_SERVICE_FIELDS
from app.serialization import CORE_VIEW_FIELDS_TO_EXPORT_FIELDS
from app.serialization import serialize_host_row_for_export
from tests.helpers import export_service_utils as es_utils
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import mocked_export_post
from tests.helpers.db_utils import db_host
from tests.helpers.test_utils import USER_IDENTITY

_LEGACY_STATIC_PROFILE = {
    "os_release": "Red Hat Enterprise Linux 9.1",
    "satellite_managed": True,
    "cloud_provider": "aws",
    "is_marketplace": False,
    "operating_system": {"name": "RHEL", "major": 9, "minor": 1},
}

_APP_DATA_TABLES = (
    "hosts_app_data_advisor",
    "hosts_app_data_vulnerability",
    "hosts_app_data_patch",
    "hosts_app_data_remediations",
    "hosts_app_data_compliance",
    "hosts_app_data_malware",
)


@contextmanager
def _capture_sql():
    queries: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        queries.append(statement)

    engine = db.session.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield queries
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def _capture_posted_body():
    captured: list[str] = []

    def capture_post(_self, url, *, data, **_kwargs):
        if hasattr(data, "decode"):
            captured.append(data.decode("utf-8"))
        else:
            captured.append(b"".join(data).decode("utf-8"))
        resp = Response()
        resp.url = url
        resp.status_code = HTTPStatus.ACCEPTED
        resp._content = b"Export successful"
        return resp

    return captured, capture_post


def _create_export(inventory_config, **message_kwargs):
    export_msg = es_utils.create_export_message_mock(**message_kwargs)
    validated_msg = parse_export_service_message(export_msg)
    base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]
    return create_export(validated_msg, base64_id, inventory_config)


def _error_body(mock_post):
    posted_data = mock_post.call_args_list[-1].kwargs.get("data") or mock_post.call_args_list[-1][1].get("data")
    return json.loads(posted_data)


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


def test_host_serialization(flask_app, db_create_host, inventory_config):
    with flask_app.app.app_context():
        expected_fields = _EXPORT_SERVICE_FIELDS
        db_create_host(host=db_host())
        identity = Identity(USER_IDENTITY)
        host_list = list(
            get_hosts_to_export(identity, rbac_filter=None, batch_size=inventory_config.export_svc_batch_size)
        )

        assert len(host_list) == 1
        assert expected_fields == list(host_list[0].keys())


def test_handle_csv_format(flask_app, db_create_host, mocker, inventory_config):
    with flask_app.app.app_context():
        db_create_host(host=db_host())
        identity = Identity(USER_IDENTITY)
        host_list = list(
            get_hosts_to_export(identity, rbac_filter=None, batch_size=inventory_config.export_svc_batch_size)
        )
        serialized_host = host_list[0]
        export_host = _format_export_data([serialized_host], "csv")

        csv_file = io.StringIO(export_host)
        mocker.patch("builtins.open", return_value=csv_file)
        export_host = es_utils.read_csv("mocked.csv")
        mocked_csv = es_utils.create_export_csv_mock(mocker)

        assert mocked_csv == export_host


def test_handle_json_format(flask_app, db_create_host, mocker, inventory_config):
    with flask_app.app.app_context():
        db_create_host(host=db_host())
        identity = Identity(USER_IDENTITY)
        host_list = list(
            get_hosts_to_export(identity, rbac_filter=None, batch_size=inventory_config.export_svc_batch_size)
        )
        serialized_host = host_list[0]

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
        assert threadctx.request_id == "9becbc61-49a4-49be-beb1-1f0a7cbc6e36"


def test_export_handle_message_sets_request_id_for_logs(flask_app, mocker, export_service_consumer_mock):
    """Export Kafka handling must populate threadctx.request_id for ContextualFilter."""
    mocker.patch("app.queue.export_service_mq.create_export", return_value=True)
    if hasattr(threadctx, "request_id"):
        delattr(threadctx, "request_id")

    expected_request_id = "9becbc61-49a4-49be-beb1-1f0a7cbc6e36"
    export_message = es_utils.create_export_message_mock()

    with flask_app.app.app_context():
        export_service_consumer_mock.handle_message(export_message)

    assert threadctx.request_id == expected_request_id

    record = logging.LogRecord(
        name="inventory.app.queue.export_service",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="You don't have the permission to access the requested resource.",
        args=(),
        exc_info=None,
    )
    ContextualFilter().filter(record)
    assert record.request_id == expected_request_id


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


def test_export_catches_db_error(flask_app, inventory_config, mocker, db_create_host):
    with flask_app.app.app_context():
        db_create_host()
        handle_export_error_mock = mocker.patch("app.queue.export_service._handle_export_error")

        real_entities_query = mocker.patch("api.host_query_db._find_hosts_entities_query")
        broken_query = mock.MagicMock()
        broken_query.outerjoin.return_value = broken_query
        broken_query.filter.return_value = broken_query
        broken_query.yield_per.return_value = broken_query
        broken_query.__iter__ = mock.Mock(side_effect=ObjectDeletedError(None))
        real_entities_query.return_value = broken_query

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

    def test_json_filters_to_custom_fields(self):
        hosts = [{"host_id": "1", "display_name": "host-a", "extra": "ignored"}]
        streamed = b"".join(_StreamingExportBody(iter(hosts), "json", export_fields=["host_id", "display_name"]))
        assert json.loads(streamed) == [{"host_id": "1", "display_name": "host-a"}]

    def test_csv_encodes_nested_dicts_as_json(self):
        hosts = [{"host_id": "1", "operating_system": {"name": "RHEL", "major": 9, "minor": 1}}]
        csv_output = b"".join(
            _StreamingExportBody(iter(hosts), "csv", export_fields=["host_id", "operating_system"])
        ).decode("utf-8")
        assert "RHEL" in csv_output


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

    def test_unauthenticated_endpoint_uses_psk(self, mocker):
        inventory_config = mocker.Mock()
        inventory_config.export_service_endpoint_authenticated = False
        inventory_config.export_service_token = "test-psk"

        _, request_headers = build_headers("dummy-identity", uuid4(), inventory_config, "json")

        assert request_headers["x-rh-exports-psk"] == "test-psk"
        assert "Authorization" not in request_headers

    def test_authenticated_endpoint_uses_kessel_token(self, mocker):
        inventory_config = mocker.Mock()
        inventory_config.export_service_endpoint_authenticated = True
        mocker.patch(
            "app.queue.export_service._get_export_service_access_token",
            return_value="kessel-token-xyz",
        )

        _, request_headers = build_headers("dummy-identity", uuid4(), inventory_config, "json")

        assert request_headers["Authorization"] == "Bearer kessel-token-xyz"
        assert "x-rh-exports-psk" not in request_headers


class TestBuildExportRequestUrl:
    """Pins the URL contract with the export service's internal API.

    The rest of the suite mocks `requests.Session.post` without inspecting the
    URL, so a malformed path would otherwise go unnoticed.
    """

    @pytest.mark.parametrize("request_type", ("upload", "error"))
    def test_uses_standardized_internal_basepath(self, request_type):
        export_uuid = uuid4()
        resource_uuid = str(uuid4())

        url = _build_export_request_url(
            "https://export-service.svc:10010", export_uuid, "inventory", resource_uuid, request_type
        )

        assert url == (
            f"https://export-service.svc:10010/internal/export/v1/"
            f"{export_uuid}/inventory/{resource_uuid}/{request_type}"
        )


@mock.patch("app.queue.export_service._handle_export_error")
@mock.patch("app.queue.export_service.build_headers", side_effect=RuntimeError("token failed"))
def test_create_export_header_build_failure_reports_error(mock_build_headers, mock_handle_error, mocker):
    """OAuth/header construction failures must notify export-service via the error endpoint."""
    inventory_config = mocker.Mock()
    inventory_config.export_service_endpoint = "http://export.test"
    inventory_config.export_service_endpoint_authenticated = False
    inventory_config.export_service_token = "test-psk"
    inventory_config.export_service_endpoint_ca_certificate = None

    validated_msg = parse_export_service_message(es_utils.create_export_message_mock())
    base64_x_rh_identity = validated_msg["data"]["resource_request"]["x_rh_identity"]

    result = create_export(validated_msg, base64_x_rh_identity, inventory_config)

    assert result is False
    mock_build_headers.assert_called_once()
    mock_handle_error.assert_called_once()
    assert mock_handle_error.call_args[0][1] == HTTPStatus.SERVICE_UNAVAILABLE
    error_headers = mock_handle_error.call_args[0][4]
    assert error_headers["x-rh-exports-psk"] == "test-psk"


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


class TestLoadViewConfig:
    def test_splits_host_kwargs_from_query_filter(self, flask_app, db_create_view):
        with flask_app.app.app_context():
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {
                        "host": {
                            "staleness": ["fresh"],
                            "tags": ["namespace/key=value"],
                            "last_check_in_start": "2025-01-01T00:00:00Z",
                        },
                        "system_profile": {"host_type": {"eq": "conventional"}},
                        "vulnerability": {"critical_cves": {"gte": 1}},
                    },
                },
                created_by="51234567",
            )
            host_filter, query_filter, columns = _load_view_config(str(view.id), "test", "51234567")

            assert host_filter == {
                "staleness": ["fresh"],
                "tags": ["namespace/key=value"],
                "last_check_in_start": "2025-01-01T00:00:00Z",
            }
            assert query_filter == {
                "system_profile": {"host_type": {"eq": "conventional"}},
                "vulnerability": {"critical_cves": {"gte": 1}},
            }
            assert columns == [{"key": "display_name"}]

    def test_empty_filters(self, flask_app, db_create_view):
        with flask_app.app.app_context():
            view = db_create_view(
                configuration={"columns": [{"key": "display_name"}]},
                created_by="51234567",
            )
            host_filter, query_filter, columns = _load_view_config(str(view.id), "test", "51234567")

            assert host_filter == {}
            assert query_filter == {}
            assert columns == [{"key": "display_name"}]

    @pytest.mark.parametrize(
        "workspace_name,expected",
        [(["my-group"], ["my-group"]), ("single-group", ["single-group"])],
    )
    def test_workspace_name_normalized_to_group_name(self, flask_app, db_create_view, workspace_name, expected):
        with flask_app.app.app_context():
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": {"workspace_name": workspace_name}},
                },
                created_by="51234567",
            )
            host_filter, _, _ = _load_view_config(str(view.id), "test", "51234567")

            assert "workspace_name" not in host_filter
            assert host_filter["group_name"] == expected


class TestCreateExportWithView:
    @mock.patch("requests.Session.post", autospec=True)
    def test_export_with_nonexistent_view_returns_error(self, mock_post, flask_app, db_create_host, inventory_config):
        with flask_app.app.app_context():
            db_create_host()
            mock_post.return_value.status_code = HTTPStatus.ACCEPTED
            mock_post.return_value.text = ""

            assert _create_export(inventory_config, filters={"view_id": str(uuid4())}) is False
            assert _error_body(mock_post)["error"] == 404

    @mock.patch("requests.Session.post", autospec=True)
    def test_export_with_view_no_user_id_returns_error(
        self, mock_post, flask_app, db_create_host, db_create_view, inventory_config
    ):
        with flask_app.app.app_context():
            db_create_host()
            view = db_create_view(
                configuration={"columns": [{"key": "display_name"}]},
                created_by="51234567",
            )
            mock_post.return_value.status_code = HTTPStatus.ACCEPTED
            mock_post.return_value.text = ""

            assert (
                _create_export(
                    inventory_config,
                    filters={"view_id": str(view.id)},
                    x_rh_identity=es_utils.X_RH_IDENTITY_NO_USER_ID,
                )
                is False
            )
            assert _error_body(mock_post)["error"] == 403

    def test_export_with_view_app_data_columns(
        self, flask_app, db_create_host, db_create_host_app_data, db_create_view, inventory_config
    ):
        captured, capture_post = _capture_posted_body()
        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            host1 = db_create_host(host=db_host(display_name="host-1"))
            host2 = db_create_host(host=db_host(display_name="host-2"))
            host1_id = str(host1.id)
            host2_id = str(host2.id)
            db_create_host_app_data(host1_id, "test", "advisor", recommendations=5)
            view = db_create_view(
                configuration={"columns": [{"key": "display_name"}, {"key": "advisor:recommendations"}]},
                created_by="51234567",
            )

            assert _create_export(
                inventory_config,
                filters={"view_id": str(view.id)},
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )

            by_id = {row["host_id"]: row for row in json.loads(captured[0])}
            expected_keys = ["host_id", "display_name", "advisor:recommendations"]
            assert list(by_id[host1_id].keys()) == expected_keys
            assert by_id[host1_id]["advisor:recommendations"] == 5
            assert by_id[host2_id]["advisor:recommendations"] is None

    def test_export_with_view_columns_csv_format(
        self, flask_app, db_create_host, db_create_host_app_data, db_create_view, inventory_config
    ):
        captured, capture_post = _capture_posted_body()
        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            host1 = db_create_host(host=db_host(display_name="host-1"))
            host1_id = str(host1.id)
            db_create_host_app_data(host1_id, "test", "advisor", recommendations=12)
            view = db_create_view(
                configuration={"columns": [{"key": "display_name"}, {"key": "advisor:recommendations"}]},
                created_by="51234567",
            )

            assert _create_export(
                inventory_config,
                format="csv",
                filters={"view_id": str(view.id)},
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )

            lines = captured[0].strip().splitlines()
            assert lines[0] == '"host_id","display_name","advisor:recommendations"'
            assert f'"{host1_id}","host-1",12' in lines[1]

    def test_export_with_view_omits_unauthorized_app_columns(
        self, flask_app, db_create_host, db_create_host_app_data, db_create_view, inventory_config
    ):
        captured, capture_post = _capture_posted_body()
        with (
            flask_app.app.app_context(),
            mock.patch("requests.Session.post", new=capture_post),
            mock.patch("app.queue.export_service.get_allowed_app_services", return_value={"advisor"}),
        ):
            host1 = db_create_host(host=db_host(display_name="host-1"))
            db_create_host_app_data(str(host1.id), "test", "advisor", recommendations=5)
            db_create_host_app_data(str(host1.id), "test", "vulnerability", total_cves=10)
            view = db_create_view(
                configuration={
                    "columns": [
                        {"key": "display_name"},
                        {"key": "advisor:recommendations"},
                        {"key": "vulnerability:total_cves"},
                    ],
                },
                created_by="51234567",
            )

            assert _create_export(
                inventory_config,
                filters={"view_id": str(view.id)},
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )

            parsed = json.loads(captured[0])
            assert list(parsed[0].keys()) == ["host_id", "display_name", "advisor:recommendations"]
            assert parsed[0]["advisor:recommendations"] == 5

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_export_with_view_rejects_unauthorized_app_filter(
        self, mock_handle_error, flask_app, db_create_view, inventory_config
    ):
        with (
            flask_app.app.app_context(),
            mock.patch("app.queue.export_service.get_allowed_app_services", return_value={"advisor"}),
        ):
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {"vulnerability": {"total_cves": {"gte": 1}}},
                },
                created_by="51234567",
            )

            assert (
                _create_export(
                    inventory_config,
                    filters={"view_id": str(view.id)},
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 403
            assert "Insufficient permissions" in mock_handle_error.call_args[0][0]


class TestResolveExportColumns:
    def test_empty_columns_returns_defaults(self, flask_app):
        with flask_app.app.app_context():
            fields, app_data = resolve_export_columns([])
            assert fields == _EXPORT_SERVICE_FIELDS
            assert app_data == {}

    def test_ui_core_columns_mapped_to_system_profile_fields(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "operating_system"},
                {"key": "infrastructure"},
                {"key": "vendor"},
                {"key": "workload"},
                {"key": "status"},
                {"key": "per_reporter_staleness"},
            ]
            fields, app_data = resolve_export_columns(columns)

            assert fields == [
                "host_id",
                "os_release",
                "infrastructure_type",
                "infrastructure_vendor",
                "workloads",
                "state",
                "data_collector",
            ]
            assert app_data == {}

    def test_all_systems_view_picker_columns_are_exported(self, flask_app):
        """Every column in the Systems View picker must resolve to at least one export field."""
        picker_keys = (
            "display_name",
            "group_name",
            "tags",
            "operating_system",
            "last_check_in",
            "status",
            "infrastructure",
            "vendor",
            "workload",
            "created",
            "per_reporter_staleness",
            "patch:advisories_rhsa_installable",
            "patch:template_name",
            "advisor:recommendations",
            "advisor:incidents",
            "vulnerability:total_cves",
            "vulnerability:critical_cves",
            "vulnerability:important_cves",
            "vulnerability:cves_with_security_rules",
            "vulnerability:cves_with_known_exploits",
            "malware:last_status",
            "malware:total_matches",
            "malware:last_scan",
            "compliance:policies_count",
            "compliance:last_scan",
        )

        with flask_app.app.app_context():
            fields, _ = resolve_export_columns([{"key": key} for key in picker_keys])

            dropped = []
            for key in picker_keys:
                mapped = CORE_VIEW_FIELDS_TO_EXPORT_FIELDS.get(key)
                if mapped:
                    if any(field not in fields for field in mapped):
                        dropped.append(key)
                elif key not in fields:
                    dropped.append(key)

            assert dropped == [], f"View columns dropped from export: {dropped}"

    def test_app_data_columns_parsed_in_order(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "tags"},
                {"key": "display_name"},
                {"key": "advisor:recommendations"},
                {"key": "vulnerability:critical_cves"},
            ]
            fields, app_data = resolve_export_columns(columns)

            assert fields == [
                "host_id",
                "tags",
                "display_name",
                "advisor:recommendations",
                "vulnerability:critical_cves",
            ]
            assert app_data == {
                "advisor": ["recommendations"],
                "vulnerability": ["critical_cves"],
            }

    @pytest.mark.parametrize("key", ["nonexistent_app:some_field", "advisor:nonexistent_field"])
    def test_unknown_columns_ignored(self, flask_app, key):
        with flask_app.app.app_context():
            fields, app_data = resolve_export_columns([{"key": "display_name"}, {"key": key}])
            assert key not in fields
            assert app_data == {}

    def test_duplicate_columns_deduplicated(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "display_name"},
                {"key": "display_name"},
                {"key": "advisor:recommendations"},
                {"key": "advisor:recommendations"},
            ]
            fields, app_data = resolve_export_columns(columns)

            assert fields == ["host_id", "display_name", "advisor:recommendations"]
            assert app_data == {"advisor": ["recommendations"]}

    def test_resolve_export_columns_allowed_apps_none_allows_all(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "display_name"},
                {"key": "advisor:recommendations"},
                {"key": "vulnerability:total_cves"},
            ]
            fields, app_data = resolve_export_columns(columns, allowed_apps=None)

            assert fields == ["host_id", "display_name", "advisor:recommendations", "vulnerability:total_cves"]
            assert app_data == {"advisor": ["recommendations"], "vulnerability": ["total_cves"]}


def _export_row(**overrides):
    values = dict(
        id=uuid4(),
        groups=None,
        last_check_in=None,
        modified_on=None,
        created_on=None,
        reporters=None,
        per_reporter_staleness=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class TestSerializeHostRowForExport:
    @pytest.mark.parametrize(
        "per_reporter_staleness, expected",
        [
            ({"puptoo": "t"}, "insights-client"),
            ({"rhsm-conduit": "t"}, "subscription-manager"),
            ({"rhsm-system-profile-bridge": "t"}, "subscription-manager"),
            ({"satellite": "t"}, "Satellite"),
            ({"discovery": "t"}, "Discovery"),
            ({"yupana": "t"}, "yupana"),
            (
                {"puptoo": "t", "yupana": "t"},
                "insights-client, yupana",
            ),
            (
                {"puptoo": "t", "rhsm-conduit": "t", "rhsm-system-profile-bridge": "t"},
                "insights-client, subscription-manager",
            ),
            ({}, None),
        ],
    )
    def test_data_collector_uses_frontend_labels(self, per_reporter_staleness, expected):
        result = serialize_host_row_for_export(
            _export_row(per_reporter_staleness=per_reporter_staleness),
            staleness={},
            fields=["host_id", "data_collector"],
        )

        assert result["data_collector"] == expected


class TestGetHostsToExportWithColumns:
    def test_default_export_left_joins_static_profile_once(self, flask_app, db_create_host):
        """RHINENG-29090: legacy export fetches static profile via one LEFT JOIN, not N+1."""
        with flask_app.app.app_context():
            for _ in range(5):
                db_create_host(extra_data={"system_profile_facts": _LEGACY_STATIC_PROFILE})
            identity = Identity(USER_IDENTITY)

            with _capture_sql() as queries:
                results = list(get_hosts_to_export(identity))

            assert len(results) == 5
            assert list(results[0].keys()) == _EXPORT_SERVICE_FIELDS
            assert results[0]["os_release"] == "Red Hat Enterprise Linux 9.1"
            assert results[0]["satellite_managed"] is True
            static_queries = [q for q in queries if "system_profiles_static" in q]
            assert len(static_queries) == 1
            assert "LEFT OUTER JOIN" in static_queries[0].upper()
            assert not any("system_profiles_dynamic" in q for q in queries)
            assert not any(table in q for q in queries for table in _APP_DATA_TABLES)

    def test_inventory_only_view_omits_system_profile_fields(self, flask_app, db_create_host):
        with flask_app.app.app_context():
            db_create_host(extra_data={"system_profile_facts": _LEGACY_STATIC_PROFILE})
            identity = Identity(USER_IDENTITY)
            export_fields = ["host_id", "display_name", "group_name"]

            with _capture_sql() as queries:
                results = list(get_hosts_to_export(identity, export_fields=export_fields))

            assert len(results) == 1
            assert list(results[0].keys()) == export_fields
            assert "os_release" not in results[0]
            assert "workloads" not in results[0]
            assert not any("system_profiles_static" in q for q in queries)
            assert not any("system_profiles_dynamic" in q for q in queries)

    def test_app_data_columns_are_not_joined_on_hosts_scan(self, flask_app, db_create_host, db_create_host_app_data):
        with flask_app.app.app_context():
            host = db_create_host(host=db_host(display_name="app-host"))
            db_create_host_app_data(str(host.id), "test", "advisor", recommendations=7)
            identity = Identity(USER_IDENTITY)

            with _capture_sql() as queries:
                results = list(
                    get_hosts_to_export(
                        identity,
                        export_fields=["host_id", "advisor:recommendations"],
                        app_data_fields={"advisor": ["recommendations"]},
                    )
                )

            assert results[0]["advisor:recommendations"] == 7
            joined_app = [q for q in queries if "JOIN" in q.upper() and any(table in q for table in _APP_DATA_TABLES)]
            assert joined_app == []
            advisor_lookups = [q for q in queries if "hosts_app_data_advisor" in q]
            assert len(advisor_lookups) == 1
            assert not any("hosts_app_data_vulnerability" in q for q in queries)

    def test_app_data_batch_with_yield_per(self, flask_app, db_create_host, db_create_host_app_data):
        """App-data lookups must work while yield_per still holds a server-side cursor."""
        with flask_app.app.app_context():
            expected = {}
            for i in range(3):
                host = db_create_host(host=db_host(display_name=f"batch-host-{i}"))
                host_id = str(host.id)
                db_create_host_app_data(host_id, "test", "advisor", recommendations=i + 1)
                expected[host_id] = i + 1

            identity = Identity(USER_IDENTITY)
            with _capture_sql() as queries:
                results = list(
                    get_hosts_to_export(
                        identity,
                        batch_size=1,
                        export_fields=["host_id", "advisor:recommendations"],
                        app_data_fields={"advisor": ["recommendations"]},
                    )
                )

            assert {row["host_id"]: row["advisor:recommendations"] for row in results} == expected
            advisor_lookups = [q for q in queries if "hosts_app_data_advisor" in q]
            assert len(advisor_lookups) == 3

    def test_app_data_filter_joins_only_filtered_app(self, flask_app, db_create_host, db_create_host_app_data):
        with flask_app.app.app_context():
            match = db_create_host(host=db_host(display_name="match"))
            db_create_host(host=db_host(display_name="skip"))
            db_create_host_app_data(str(match.id), "test", "advisor", recommendations=9)
            identity = Identity(USER_IDENTITY)
            query_filter = {"advisor": {"recommendations": {"gte": 1}}}

            with _capture_sql() as queries:
                results = list(
                    get_hosts_to_export(
                        identity,
                        export_fields=["host_id", "display_name"],
                        query_filter=query_filter,
                    )
                )

            assert [r["display_name"] for r in results] == ["match"]
            joined = [q for q in queries if "LEFT OUTER JOIN" in q.upper() and "hosts_app_data_advisor" in q]
            assert len(joined) == 1
            assert "hosts_app_data_vulnerability" not in joined[0]
            assert "hosts_app_data_patch" not in joined[0]
            assert not any("hosts_app_data_vulnerability" in q for q in queries)

    def test_workloads_column_extracts_root_keys(self, flask_app, db_create_host):
        with flask_app.app.app_context():
            db_create_host(
                extra_data={
                    "system_profile_facts": {
                        "workloads": {
                            "ansible": {"controller_version": "2.4"},
                            "satellite": {"version": "6.15"},
                        }
                    }
                }
            )
            identity = Identity(USER_IDENTITY)
            export_fields = ["host_id", "workloads"]
            results = list(get_hosts_to_export(identity, export_fields=export_fields))

            assert len(results) == 1
            assert results[0]["workloads"] == "ansible, satellite"

    def test_compliance_policies_column_extracts_names(self, flask_app, db_create_host, db_create_host_app_data):
        with flask_app.app.app_context():
            host = db_create_host(host=db_host(display_name="compliance-host"))
            policies = [
                {"id": "d4722d4e-d290-4822-b8d2-8046b0cf2340", "name": "Policy 1"},
                {"id": "e728dc3b-da2d-48a2-9ea7-222fc6f27871", "name": "Policy 2"},
            ]
            db_create_host_app_data(str(host.id), "test", "compliance", policies=policies)
            identity = Identity(USER_IDENTITY)
            export_fields = ["host_id", "compliance:policies"]
            app_data_fields = {"compliance": ["policies"]}
            results = list(
                get_hosts_to_export(
                    identity,
                    export_fields=export_fields,
                    app_data_fields=app_data_fields,
                )
            )

            assert len(results) == 1
            assert results[0]["compliance:policies"] == "Policy 1, Policy 2"


class TestFormatCompliancePolicies:
    def test_edge_cases(self):
        assert _format_compliance_policies([]) is None
        assert _format_compliance_policies(None) is None
        assert _format_compliance_policies([{"id": "d4722d4e-d290-4822-b8d2-8046b0cf2340"}]) == (
            "d4722d4e-d290-4822-b8d2-8046b0cf2340"
        )
        assert _format_compliance_policies("Policy 1, Policy 2") == "Policy 1, Policy 2"


class TestExportProfileJoins:
    def test_sp_filter_joins_even_without_sp_columns(self):
        query_filter = {"system_profile": {"os_release": {"eq": "8.10"}}}
        need_static, need_dynamic = _export_needs_profile_joins(["host_id", "display_name"], query_filter)
        assert need_static is True
        assert need_dynamic is False
