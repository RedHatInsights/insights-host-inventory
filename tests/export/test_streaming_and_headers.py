import json
from http import HTTPStatus
from uuid import uuid4

import pytest

from app.exceptions import InventoryException
from app.queue.export_service import _format_export_data
from app.queue.export_service import _handle_export_response
from app.queue.export_service import _StreamingExportBody
from app.queue.export_service import build_headers
from tests.helpers.export_service_utils import make_response


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
        _handle_export_response(make_response(HTTPStatus.ACCEPTED, "payload delivered"), uuid4(), "json")

    @pytest.mark.parametrize(
        "status_code",
        [HTTPStatus.BAD_REQUEST, HTTPStatus.CONFLICT, HTTPStatus.INTERNAL_SERVER_ERROR],
    )
    def test_already_processed_does_not_raise(self, status_code):
        resp = make_response(
            status_code,
            '{"detail": "this resource has already been processed", "status": 400}',
        )
        _handle_export_response(resp, uuid4(), "csv")

    def test_other_400_still_raises(self):
        resp = make_response(HTTPStatus.BAD_REQUEST, '{"detail": "some other error"}')
        with pytest.raises(InventoryException):
            _handle_export_response(resp, uuid4(), "json")

    def test_server_error_raises(self):
        resp = make_response(HTTPStatus.INTERNAL_SERVER_ERROR, "internal error")
        with pytest.raises(InventoryException):
            _handle_export_response(resp, uuid4(), "json")


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
