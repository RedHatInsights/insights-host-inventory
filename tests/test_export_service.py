import io
import json
from contextlib import contextmanager
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from http import HTTPStatus
from unittest import mock
from uuid import uuid4

import pytest
from marshmallow.exceptions import ValidationError
from requests import Response
from sqlalchemy import event
from sqlalchemy.orm.exc import ObjectDeletedError

from api.host_query_db import _app_models_needed_for_filter
from api.host_query_db import _export_needs_profile_joins
from api.host_query_db import get_hosts_to_export
from app.auth.identity import Identity
from app.exceptions import InventoryException
from app.models import db
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

    def test_workspace_name_normalized_to_group_name(self, flask_app, db_create_view):
        with flask_app.app.app_context():
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": {"workspace_name": ["my-group"]}},
                },
                created_by="51234567",
            )
            host_filter, query_filter, columns = _load_view_config(str(view.id), "test", "51234567")

            assert "workspace_name" not in host_filter
            assert host_filter["group_name"] == ["my-group"]
            assert columns == [{"key": "display_name"}]

    def test_workspace_name_string_wrapped_in_list(self, flask_app, db_create_view):
        with flask_app.app.app_context():
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": {"workspace_name": "single-group"}},
                },
                created_by="51234567",
            )
            host_filter, _, columns = _load_view_config(str(view.id), "test", "51234567")

            assert host_filter["group_name"] == ["single-group"]
            assert columns == [{"key": "display_name"}]

    def test_view_not_found_raises(self, flask_app):
        from lib.views_repository import ViewNotFoundError

        with flask_app.app.app_context():
            with pytest.raises(ViewNotFoundError):
                _load_view_config(str(uuid4()), "test", "51234567")


class TestCreateExportWithView:
    @mock.patch("requests.Session.post", new=mocked_export_post)
    def test_export_with_view_filters(self, flask_app, db_create_host, db_create_view, inventory_config):
        """Export with a view_id applies the view's saved filters."""
        with flask_app.app.app_context():
            db_create_host()
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": {"staleness": ["fresh"]}},
                },
                created_by="51234567",
            )

            export_msg = es_utils.create_export_message_mock(
                filters={"view_id": str(view.id)},
            )
            validated_msg = parse_export_service_message(export_msg)
            base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]

            result = create_export(validated_msg, base64_id, inventory_config)
            assert result is True

    @mock.patch("requests.Session.post", autospec=True)
    def test_export_with_nonexistent_view_returns_error(self, mock_post, flask_app, db_create_host, inventory_config):
        """Export with an invalid view_id reports a 404 error."""
        with flask_app.app.app_context():
            db_create_host()
            mock_post.return_value.status_code = HTTPStatus.ACCEPTED
            mock_post.return_value.text = ""

            export_msg = es_utils.create_export_message_mock(
                filters={"view_id": str(uuid4())},
            )
            validated_msg = parse_export_service_message(export_msg)
            base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]

            result = create_export(validated_msg, base64_id, inventory_config)
            assert result is False

            error_call = mock_post.call_args_list[-1]
            posted_data = error_call.kwargs.get("data") or error_call[1].get("data")
            error_body = json.loads(posted_data)
            assert error_body["error"] == 404

    @mock.patch("requests.Session.post", autospec=True)
    def test_export_with_view_no_user_id_returns_error(
        self, mock_post, flask_app, db_create_host, db_create_view, inventory_config
    ):
        """Export with view_id but identity lacking user_id reports a 403."""
        with flask_app.app.app_context():
            db_create_host()
            view = db_create_view(
                configuration={"columns": [{"key": "display_name"}]},
                created_by="51234567",
            )
            mock_post.return_value.status_code = HTTPStatus.ACCEPTED
            mock_post.return_value.text = ""

            export_msg = es_utils.create_export_message_mock(
                filters={"view_id": str(view.id)},
                x_rh_identity=es_utils.X_RH_IDENTITY_NO_USER_ID,
            )
            validated_msg = parse_export_service_message(export_msg)
            base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]

            result = create_export(validated_msg, base64_id, inventory_config)
            assert result is False

            error_call = mock_post.call_args_list[-1]
            posted_data = error_call.kwargs.get("data") or error_call[1].get("data")
            error_body = json.loads(posted_data)
            assert error_body["error"] == 403

    @mock.patch("requests.Session.post", new=mocked_export_post)
    def test_export_without_view_backward_compat(self, flask_app, db_create_host, inventory_config):
        """Export without view_id still works (backward compatibility)."""
        with flask_app.app.app_context():
            db_create_host()

            export_msg = es_utils.create_export_message_mock(filters={})
            validated_msg = parse_export_service_message(export_msg)
            base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]

            result = create_export(validated_msg, base64_id, inventory_config)
            assert result is True

    def test_export_without_view_includes_legacy_system_profile_fields(
        self, flask_app, db_create_host, inventory_config
    ):
        """Hosts-table export (no view_id) still includes static system-profile fields."""
        captured_data = []

        def capture_post(_self, url, *, data, **_kwargs):
            if hasattr(data, "decode"):
                captured_data.append(data.decode("utf-8"))
            else:
                captured_data.append(b"".join(data).decode("utf-8"))
            resp = Response()
            resp.url = url
            resp.status_code = HTTPStatus.ACCEPTED
            resp._content = b"Export successful"
            return resp

        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            db_create_host(extra_data={"system_profile_facts": _LEGACY_STATIC_PROFILE})

            export_msg = es_utils.create_export_message_mock(filters={})
            validated_msg = parse_export_service_message(export_msg)
            base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]

            result = create_export(validated_msg, base64_id, inventory_config)
            assert result is True
            assert len(captured_data) == 1

            parsed = json.loads(captured_data[0])
            assert len(parsed) == 1
            assert list(parsed[0].keys()) == _EXPORT_SERVICE_FIELDS
            assert parsed[0]["os_release"] == "Red Hat Enterprise Linux 9.1"
            assert parsed[0]["satellite_managed"] is True
            assert parsed[0]["cloud_provider"] == "aws"
            assert parsed[0]["is_marketplace"] is False

    @mock.patch("requests.Session.post", new=mocked_export_post)
    def test_export_with_view_columns(self, flask_app, db_create_host, db_create_view, inventory_config):
        """Export with a view_id uses the view's column configuration."""
        with flask_app.app.app_context():
            db_create_host()
            view = db_create_view(
                configuration={
                    "columns": [
                        {"key": "display_name"},
                        {"key": "operating_system"},
                        {"key": "tags"},
                    ],
                },
                created_by="51234567",
            )

            export_msg = es_utils.create_export_message_mock(
                filters={"view_id": str(view.id)},
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )
            validated_msg = parse_export_service_message(export_msg)
            base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]

            result = create_export(validated_msg, base64_id, inventory_config)
            assert result is True

    def test_export_with_view_app_data_columns(
        self, flask_app, db_create_host, db_create_host_app_data, db_create_view, inventory_config
    ):
        """Export with a view containing app-data columns populates app-data values and nulls."""
        captured_data = []

        def capture_post(_self, url, *, data, **_kwargs):
            if hasattr(data, "decode"):
                captured_data.append(data.decode("utf-8"))
            else:
                captured_data.append(b"".join(data).decode("utf-8"))
            resp = Response()
            resp.url = url
            resp.status_code = HTTPStatus.ACCEPTED
            resp._content = b"Export successful"
            return resp

        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            host1 = db_create_host(host=db_host(display_name="host-1"))
            host2 = db_create_host(host=db_host(display_name="host-2"))
            host1_id = str(host1.id)
            host2_id = str(host2.id)
            db_create_host_app_data(host1_id, "test", "advisor", recommendations=5)

            view = db_create_view(
                configuration={
                    "columns": [
                        {"key": "display_name"},
                        {"key": "advisor:recommendations"},
                    ],
                },
                created_by="51234567",
            )

            export_msg = es_utils.create_export_message_mock(
                filters={"view_id": str(view.id)},
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )
            validated_msg = parse_export_service_message(export_msg)
            base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]

            result = create_export(validated_msg, base64_id, inventory_config)
            assert result is True
            assert len(captured_data) == 1

            parsed = json.loads(captured_data[0])
            assert len(parsed) == 2
            h1 = next(h for h in parsed if h["host_id"] == host1_id)
            h2 = next(h for h in parsed if h["host_id"] == host2_id)

            assert h1["display_name"] == "host-1"
            assert h1["advisor:recommendations"] == 5
            assert h2["display_name"] == "host-2"
            assert h2["advisor:recommendations"] is None

            # Keys must follow view column order starting with host_id
            expected_keys = ["host_id", "display_name", "advisor:recommendations"]
            assert list(h1.keys()) == expected_keys
            assert list(h2.keys()) == expected_keys

    def test_export_with_view_columns_csv_format(
        self, flask_app, db_create_host, db_create_host_app_data, db_create_view, inventory_config
    ):
        """Export in CSV format with view columns generates matching header and rows."""
        captured_data = []

        def capture_post(_self, url, *, data, **_kwargs):
            if hasattr(data, "decode"):
                captured_data.append(data.decode("utf-8"))
            else:
                captured_data.append(b"".join(data).decode("utf-8"))
            resp = Response()
            resp.url = url
            resp.status_code = HTTPStatus.ACCEPTED
            resp._content = b"Export successful"
            return resp

        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            host1 = db_create_host(host=db_host(display_name="host-1"))
            host1_id = str(host1.id)
            db_create_host_app_data(host1_id, "test", "advisor", recommendations=12)

            view = db_create_view(
                configuration={
                    "columns": [
                        {"key": "display_name"},
                        {"key": "advisor:recommendations"},
                    ],
                },
                created_by="51234567",
            )

            export_msg = es_utils.create_export_message_mock(
                format="csv",
                filters={"view_id": str(view.id)},
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )
            validated_msg = parse_export_service_message(export_msg)
            base64_id = validated_msg["data"]["resource_request"]["x_rh_identity"]

            result = create_export(validated_msg, base64_id, inventory_config)
            assert result is True
            assert len(captured_data) == 1

            lines = captured_data[0].strip().splitlines()
            assert len(lines) == 2
            assert lines[0] == '"host_id","display_name","advisor:recommendations"'
            assert f'"{host1_id}","host-1",12' in lines[1]


class TestResolveExportColumns:
    def test_empty_columns_returns_defaults(self, flask_app):
        with flask_app.app.app_context():
            fields, app_data = resolve_export_columns([])
            assert fields == _EXPORT_SERVICE_FIELDS
            assert app_data == {}

    def test_core_columns_mapped(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "display_name"},
                {"key": "operating_system"},
                {"key": "tags"},
                {"key": "status"},
            ]
            fields, app_data = resolve_export_columns(columns)

            assert "host_id" in fields
            assert "display_name" in fields
            assert "operating_system" in fields
            assert "tags" in fields
            assert "state" in fields
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
                "operating_system",
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
            # Inventory
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
            # Content
            "patch:advisories_rhsa_installable",
            "patch:template_name",
            # Advisor
            "advisor:recommendations",
            "advisor:incidents",
            # Vulnerability
            "vulnerability:total_cves",
            "vulnerability:critical_cves",
            "vulnerability:important_cves",
            "vulnerability:cves_with_security_rules",
            "vulnerability:cves_with_known_exploits",
            # Malware
            "malware:last_status",
            "malware:total_matches",
            "malware:last_scan",
            # Compliance
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

    def test_app_data_columns_parsed(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "display_name"},
                {"key": "advisor:recommendations"},
                {"key": "vulnerability:critical_cves"},
            ]
            fields, app_data = resolve_export_columns(columns)

            assert "host_id" in fields
            assert "display_name" in fields
            assert "advisor:recommendations" in fields
            assert "vulnerability:critical_cves" in fields
            assert app_data == {
                "advisor": ["recommendations"],
                "vulnerability": ["critical_cves"],
            }

    def test_column_order_preserved(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "tags"},
                {"key": "display_name"},
                {"key": "operating_system"},
            ]
            fields, _ = resolve_export_columns(columns)

            assert fields[0] == "host_id"
            tags_idx = fields.index("tags")
            display_idx = fields.index("display_name")
            os_idx = fields.index("operating_system")
            assert tags_idx < display_idx < os_idx

    def test_unknown_app_column_ignored(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "display_name"},
                {"key": "nonexistent_app:some_field"},
            ]
            fields, app_data = resolve_export_columns(columns)

            assert "nonexistent_app:some_field" not in fields
            assert app_data == {}

    def test_unknown_field_in_valid_app_ignored(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "display_name"},
                {"key": "advisor:nonexistent_field"},
            ]
            fields, app_data = resolve_export_columns(columns)

            assert "advisor:nonexistent_field" not in fields
            assert "advisor" not in app_data

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

    def test_group_name_exports_workspace_name_only(self, flask_app):
        with flask_app.app.app_context():
            columns = [{"key": "group_name"}]
            fields, _ = resolve_export_columns(columns)

            assert fields == ["host_id", "group_name"]


class TestStreamingExportBodyCustomFields:
    def test_csv_uses_custom_fields(self):
        custom_fields = ["host_id", "display_name", "os_release"]
        hosts = [{"host_id": "1", "display_name": "host-a", "os_release": "8.10"}]
        body = _StreamingExportBody(iter(hosts), "csv", export_fields=custom_fields)
        csv_output = b"".join(body).decode("utf-8")

        lines = csv_output.splitlines()
        assert '"host_id","display_name","os_release"' in lines[0]
        assert body.host_count == 1

    def test_json_with_custom_fields(self):
        custom_fields = ["host_id", "display_name"]
        hosts = [{"host_id": "1", "display_name": "host-a", "extra": "ignored"}]
        body = _StreamingExportBody(iter(hosts), "json", export_fields=custom_fields)
        json_output = b"".join(body).decode("utf-8")

        parsed = json.loads(json_output)
        assert parsed == [{"host_id": "1", "display_name": "host-a"}]


class TestGetHostsToExportWithColumns:
    def test_app_data_batching_and_order(self, flask_app, db_create_host, db_create_host_app_data):
        with flask_app.app.app_context():
            host = db_create_host(host=db_host(display_name="app-host"))
            host_id = str(host.id)
            db_create_host_app_data(host_id, "test", "advisor", recommendations=7)

            identity = Identity(USER_IDENTITY)
            export_fields = ["host_id", "advisor:recommendations", "display_name"]
            app_data_fields = {"advisor": ["recommendations"]}

            results = list(
                get_hosts_to_export(
                    identity,
                    export_fields=export_fields,
                    app_data_fields=app_data_fields,
                )
            )

            assert len(results) == 1
            assert results[0]["host_id"] == host_id
            assert results[0]["advisor:recommendations"] == 7
            assert results[0]["display_name"] == "app-host"
            # Key order matches export_fields even with app-data column first
            assert list(results[0].keys()) == export_fields

    def test_missing_app_data_yields_none(self, flask_app, db_create_host):
        with flask_app.app.app_context():
            host = db_create_host(host=db_host(display_name="plain-host"))
            host_id = str(host.id)

            identity = Identity(USER_IDENTITY)
            export_fields = ["host_id", "display_name", "advisor:recommendations"]
            app_data_fields = {"advisor": ["recommendations"]}

            results = list(
                get_hosts_to_export(
                    identity,
                    export_fields=export_fields,
                    app_data_fields=app_data_fields,
                )
            )

            assert len(results) == 1
            assert results[0]["host_id"] == host_id
            assert results[0]["display_name"] == "plain-host"
            assert results[0]["advisor:recommendations"] is None
            assert list(results[0].keys()) == export_fields

    def test_default_export_includes_legacy_system_profile_fields(self, flask_app, db_create_host):
        with flask_app.app.app_context():
            db_create_host(extra_data={"system_profile_facts": _LEGACY_STATIC_PROFILE})
            identity = Identity(USER_IDENTITY)
            results = list(get_hosts_to_export(identity))

            assert len(results) == 1
            assert list(results[0].keys()) == _EXPORT_SERVICE_FIELDS
            assert results[0]["os_release"] == "Red Hat Enterprise Linux 9.1"
            assert results[0]["satellite_managed"] is True
            assert results[0]["cloud_provider"] == "aws"
            assert results[0]["is_marketplace"] is False

    def test_default_export_left_joins_static_profile_once(self, flask_app, db_create_host):
        """RHINENG-29090: legacy export fetches static profile via one LEFT JOIN, not N+1."""
        with flask_app.app.app_context():
            for _ in range(5):
                db_create_host(extra_data={"system_profile_facts": _LEGACY_STATIC_PROFILE})
            identity = Identity(USER_IDENTITY)

            with _capture_sql() as queries:
                results = list(get_hosts_to_export(identity))

            assert len(results) == 5
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

    def test_os_column_uses_static_profile(self, flask_app, db_create_host):
        with flask_app.app.app_context():
            db_create_host(extra_data={"system_profile_facts": _LEGACY_STATIC_PROFILE})
            identity = Identity(USER_IDENTITY)
            export_fields = ["host_id", "operating_system"]
            results = list(get_hosts_to_export(identity, export_fields=export_fields))

            assert len(results) == 1
            assert results[0]["operating_system"]["name"] == "RHEL"
            assert results[0]["operating_system"]["major"] == 9
            assert "os_release" not in results[0]

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


class TestExportProfileJoins:
    def test_legacy_fields_need_static_join(self):
        assert _export_needs_profile_joins(_EXPORT_SERVICE_FIELDS, None) == (True, False)

    def test_inventory_only_fields_skip_joins(self):
        assert _export_needs_profile_joins(["host_id", "display_name", "group_name"], None) == (False, False)

    def test_os_column_needs_static_join(self):
        assert _export_needs_profile_joins(["host_id", "operating_system"], None) == (True, False)

    def test_workload_column_needs_dynamic_join(self):
        assert _export_needs_profile_joins(["host_id", "workloads"], None) == (False, True)

    def test_sp_filter_joins_even_without_sp_columns(self):
        query_filter = {"system_profile": {"os_release": {"eq": "8.10"}}}
        need_static, need_dynamic = _export_needs_profile_joins(["host_id", "display_name"], query_filter)
        assert need_static is True
        assert need_dynamic is False

    def test_no_app_models_without_filter(self):
        assert _app_models_needed_for_filter(None) == []
        assert _app_models_needed_for_filter({}) == []
        assert _app_models_needed_for_filter({"system_profile": {"os_release": {"eq": "8.10"}}}) == []

    def test_filter_joins_only_referenced_apps(self, flask_app):
        with flask_app.app.app_context():
            models = _app_models_needed_for_filter({"advisor": {"recommendations": {"gte": 1}}})
            assert [m.__tablename__ for m in models] == ["hosts_app_data_advisor"]
