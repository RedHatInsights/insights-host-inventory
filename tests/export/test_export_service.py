import io
import json
import logging
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from http import HTTPStatus
from unittest import mock

import pytest
from marshmallow.exceptions import ValidationError
from opentelemetry.trace import SpanKind
from sqlalchemy.orm.exc import ObjectDeletedError

from api.host_query_db import get_hosts_to_export
from app.auth.identity import Identity
from app.logging import ContextualFilter
from app.logging import threadctx
from app.queue.export_service import _format_export_data
from app.queue.export_service import _StreamingExportBody
from app.queue.export_service import create_export
from app.queue.export_service_mq import parse_export_service_message
from app.queue.host_mq import OperationResult
from app.serialization import _EXPORT_SERVICE_FIELDS
from app.telemetry import _build_rh_attribute_span_processor
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

        assert create_export(validated_msg, inventory_config)


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


@pytest.mark.parametrize(
    "parsed_message",
    [
        {"source": "other", "redhatorgid": "org-1"},
        {"source": "other", "redhatorgid": "org-1", "data": {}},
        {"source": "other", "redhatorgid": "org-1", "data": {"resource_request": {}}},
    ],
)
def test_handle_message_missing_export_request_uuid_logs_warning(
    parsed_message, flask_app, mocker, export_service_consumer_mock, caplog
):
    mocker.patch("app.queue.export_service_mq.parse_export_service_message", return_value=parsed_message)
    init_context = mocker.spy(export_service_consumer_mock, "_initialize_message_context")

    with flask_app.app.app_context(), caplog.at_level(logging.WARNING):
        resp = export_service_consumer_mock.handle_message("{}")

    assert resp is None
    assert any(
        "Export message missing export_request_uuid; logging without request_id" in record.getMessage()
        for record in caplog.records
    )
    init_context.assert_called_once_with(None, org_id="org-1")


def test_export_handle_message_preserves_span_and_log_identity(
    flask_app, mocker, export_service_consumer_mock, caplog, otel_provider
):
    """Export identity stays on the consumer span after the handler clears threadctx."""
    mocker.patch("app.queue.export_service.resolve_permission", return_value=(False, None))
    mock_post = mocker.patch("requests.Session.post", autospec=True)
    mock_post.return_value.status_code = 202

    expected_request_id = "9becbc61-49a4-49be-beb1-1f0a7cbc6e36"
    provider, exporter = otel_provider(span_processors=[_build_rh_attribute_span_processor()])
    export_logger = logging.getLogger("inventory.app.queue.export_service")
    contextual_filter = ContextualFilter()
    export_logger.addFilter(contextual_filter)
    try:
        with (
            flask_app.app.app_context(),
            caplog.at_level(logging.ERROR, logger="inventory.app.queue.export_service"),
            provider.get_tracer(__name__).start_as_current_span(
                "mq.process export", kind=SpanKind.CONSUMER, attributes={"messaging.operation.name": "process"}
            ),
        ):
            export_service_consumer_mock.handle_message(es_utils.create_export_message_mock())
            assert threadctx.request_id is None
            assert threadctx.org_id is None
    finally:
        export_logger.removeFilter(contextual_filter)

    error_records = [
        record
        for record in caplog.records
        if record.getMessage() == "You don't have the permission to access the requested resource."
    ]
    assert error_records
    assert error_records[0].request_id == expected_request_id
    span = next(span for span in exporter.get_finished_spans() if span.name == "mq.process export")
    assert span.attributes["rh.request_id"] == expected_request_id
    assert span.attributes["rh.org_id"] == "test"


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

        create_export(validated_msg, inventory_config)
        handle_export_error_mock.assert_called_once()


@mock.patch("requests.Session.post", autospec=True)
def test_create_export_posts_streaming_body(mock_post, db_create_host, flask_app, inventory_config):
    """create_export must pass a _StreamingExportBody to session.post, not a pre-materialized str/bytes."""
    with flask_app.app.app_context():
        db_create_host()

        mock_post.return_value.status_code = HTTPStatus.ACCEPTED
        mock_post.return_value.text = ""

        validated_msg = parse_export_service_message(es_utils.create_export_message_mock())

        create_export(validated_msg, inventory_config)

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

        result = create_export(validated_msg, inventory_config)
        assert result is True


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

    result = create_export(validated_msg, inventory_config)

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

        create_export(validated_msg, inventory_config)

        # The Session instance is the first positional arg (autospec=True) of the post call.
        session_instance = mock_post.call_args_list[-1][0][0]
        assert session_instance.verify == "/path/to/ca.crt"
