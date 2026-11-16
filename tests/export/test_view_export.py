import json
from contextlib import contextmanager
from http import HTTPStatus
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import pytest
from requests import Response
from sqlalchemy import event

from api.host_query_db import _export_needs_profile_joins
from api.host_query_db import get_hosts_to_export
from api.views_validation import validate_view_configuration
from app.auth.identity import Identity
from app.models import db
from app.queue.export_service import ALWAYS_APPENDED_EXPORT_FIELDS
from app.queue.export_service import COMPOSITE_VIEW_FIELDS_TO_EXPORT_FIELDS
from app.queue.export_service import _build_export_request_url
from app.queue.export_service import _format_compliance_policies
from app.queue.export_service import _handle_export_error
from app.queue.export_service import _load_view_config
from app.queue.export_service import create_export
from app.queue.export_service import resolve_export_columns
from app.queue.export_service_mq import parse_export_service_message
from app.serialization import _EXPORT_SERVICE_FIELDS
from app.serialization import CORE_VIEW_FIELDS_TO_EXPORT_FIELDS
from app.serialization import serialize_host_row_for_export
from tests.helpers import export_service_utils as es_utils
from tests.helpers.db_utils import db_host
from tests.helpers.export_service_utils import make_response
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


def _error_body(mock_post):
    posted_data = mock_post.call_args_list[-1].kwargs.get("data") or mock_post.call_args_list[-1][1].get("data")
    return json.loads(posted_data)


def _create_export(inventory_config, **message_kwargs):
    export_msg = es_utils.create_export_message_mock(**message_kwargs)
    validated_msg = parse_export_service_message(export_msg)
    return create_export(validated_msg, inventory_config)


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


class TestHandleExportError:
    def test_error_handler_does_not_propagate_post_failure(self):
        session = mock.Mock()
        session.post.side_effect = ConnectionError("network down")
        _handle_export_error("some error", 500, "http://example.com/error", session, {}, uuid4(), "json")

    def test_error_handler_does_not_propagate_response_error(self):
        session = mock.Mock()
        session.post.return_value = make_response(HTTPStatus.INTERNAL_SERVER_ERROR, "boom")
        _handle_export_error("some error", 500, "http://example.com/error", session, {}, uuid4(), "json")

    def test_error_handler_succeeds_normally(self):
        session = mock.Mock()
        session.post.return_value = make_response(HTTPStatus.ACCEPTED)
        _handle_export_error("some error", 500, "http://example.com/error", session, {}, uuid4(), "json")
        session.post.assert_called_once()


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
            host_filter, query_filter, columns, _, _ = _load_view_config(str(view.id), "test", "51234567")

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
            host_filter, query_filter, columns, _, _ = _load_view_config(str(view.id), "test", "51234567")

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
            host_filter, _, _, _, _ = _load_view_config(str(view.id), "test", "51234567")

            assert "workspace_name" not in host_filter
            assert host_filter["group_name"] == expected

    @pytest.mark.parametrize(
        "workspace_id,expected",
        [
            (["5b58be21-39f5-4c11-9c61-6ce94f5dd274"], ["5b58be21-39f5-4c11-9c61-6ce94f5dd274"]),
            ("5b58be21-39f5-4c11-9c61-6ce94f5dd274", ["5b58be21-39f5-4c11-9c61-6ce94f5dd274"]),
        ],
    )
    def test_workspace_id_normalized_to_group_ids(self, flask_app, db_create_view, workspace_id, expected):
        with flask_app.app.app_context():
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": {"workspace_id": workspace_id}},
                },
                created_by="51234567",
            )
            host_filter, _, _, _, _ = _load_view_config(str(view.id), "test", "51234567")

            assert "workspace_id" not in host_filter
            assert host_filter["group_ids"] == expected

    def test_extracts_sort(self, flask_app, db_create_view):
        with flask_app.app.app_context():
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "sort": {"key": "display_name", "direction": "desc"},
                },
                created_by="51234567",
            )
            _, _, _, order_by, order_how = _load_view_config(str(view.id), "test", "51234567")

            assert order_by == "display_name"
            assert order_how == "DESC"

    def test_no_sort_returns_none(self, flask_app, db_create_view):
        with flask_app.app.app_context():
            view = db_create_view(
                configuration={"columns": [{"key": "display_name"}]},
                created_by="51234567",
            )
            _, _, _, order_by, order_how = _load_view_config(str(view.id), "test", "51234567")

            assert order_by is None
            assert order_how is None


class TestWorkspaceFilterValidation:
    def test_workspace_id_accepts_bare_string(self, flask_app):
        """Inline configurations may carry a bare-string workspace_id (rather than a
        list), mirroring how workspace_name values are normalized."""
        with flask_app.app.app_context():
            validate_view_configuration(
                {
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": {"workspace_id": "5b58be21-39f5-4c11-9c61-6ce94f5dd274"}},
                }
            )

    def test_workspace_id_accepts_uuid_list(self, flask_app):
        with flask_app.app.app_context():
            validate_view_configuration(
                {
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": {"workspace_id": ["5b58be21-39f5-4c11-9c61-6ce94f5dd274"]}},
                }
            )

    def test_workspace_name_alone_is_still_valid(self, flask_app):
        """The legacy name-matched filter keeps working on its own."""
        with flask_app.app.app_context():
            validate_view_configuration(
                {
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": {"workspace_name": ["my-group"]}},
                }
            )


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
            db_create_host_app_data(
                host1_id, "test", "advisor", recommendations=5, critical=2, important=1, moderate=3, low=0
            )
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
            expected_keys = [
                "host_id",
                "display_name",
                "advisor:critical",
                "advisor:important",
                "advisor:moderate",
                "advisor:low",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert list(by_id[host1_id].keys()) == expected_keys
            assert by_id[host1_id]["advisor:critical"] == 2
            assert by_id[host1_id]["advisor:low"] == 0
            assert by_id[host2_id]["advisor:critical"] is None

    def test_export_with_view_columns_csv_format(
        self, flask_app, db_create_host, db_create_host_app_data, db_create_view, inventory_config
    ):
        captured, capture_post = _capture_posted_body()
        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            host1 = db_create_host(host=db_host(display_name="host-1"))
            host1_id = str(host1.id)
            db_create_host_app_data(
                host1_id, "test", "advisor", recommendations=12, critical=1, important=2, moderate=3, low=4
            )
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
            expected_header_fields = [
                "host_id",
                "display_name",
                "advisor:critical",
                "advisor:important",
                "advisor:moderate",
                "advisor:low",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert lines[0] == ",".join(f'"{field}"' for field in expected_header_fields)
            assert f'"{host1_id}","host-1",1,2,3,4' in lines[1]

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
            db_create_host_app_data(str(host1.id), "test", "advisor", recommendations=5, critical=2, important=1)
            db_create_host_app_data(str(host1.id), "test", "vulnerability", total_cves=10, critical_cves=7)
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
            assert list(parsed[0].keys()) == [
                "host_id",
                "display_name",
                "advisor:critical",
                "advisor:important",
                "advisor:moderate",
                "advisor:low",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert parsed[0]["advisor:critical"] == 2

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

    @pytest.mark.parametrize(
        "host_filters",
        [
            {"recommendation_severity": ["critical"]},
            {"incident_status": ["present"]},
            {"recommendation_severity": ["critical", "not_analyzed"], "incident_status": ["not_present"]},
        ],
    )
    @mock.patch("app.queue.export_service._handle_export_error")
    def test_export_with_view_rejects_unauthorized_advisor_host_filters(
        self, mock_handle_error, flask_app, db_create_view, inventory_config, host_filters
    ):
        with (
            flask_app.app.app_context(),
            mock.patch("app.queue.export_service.get_allowed_app_services", return_value=set()),
        ):
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": host_filters},
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
            assert "Insufficient permissions to filter by advisor" in mock_handle_error.call_args[0][0]

    @pytest.mark.parametrize(
        "host_filters",
        [
            {"installable_advisory_type": ["security"]},
            {"template": "present"},
            {"installable_advisory_type": ["not_evaluated"], "template": "not_present"},
        ],
    )
    @mock.patch("app.queue.export_service._handle_export_error")
    def test_export_with_view_rejects_unauthorized_patch_host_filters(
        self, mock_handle_error, flask_app, db_create_view, inventory_config, host_filters
    ):
        with (
            flask_app.app.app_context(),
            mock.patch("app.queue.export_service.get_allowed_app_services", return_value=set()),
        ):
            view = db_create_view(
                configuration={
                    "columns": [{"key": "display_name"}],
                    "filters": {"host": host_filters},
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
            assert "Insufficient permissions to filter by patch" in mock_handle_error.call_args[0][0]


class TestCreateExportWithInlineConfiguration:
    """Inline configuration carries the table's live (possibly unsaved) WYSIWYG state."""

    def test_inline_config_respects_columns(
        self, flask_app, db_create_host, db_create_host_app_data, inventory_config
    ):
        captured, capture_post = _capture_posted_body()
        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            host1 = db_create_host(host=db_host(display_name="host-1"))
            db_create_host_app_data(
                str(host1.id), "test", "advisor", recommendations=7, critical=4, important=3, moderate=2, low=1
            )

            assert _create_export(
                inventory_config,
                filters={
                    "configuration": {
                        "columns": [{"key": "display_name"}, {"key": "advisor:recommendations"}],
                    }
                },
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )

            parsed = json.loads(captured[0])
            assert list(parsed[0].keys()) == [
                "host_id",
                "display_name",
                "advisor:critical",
                "advisor:important",
                "advisor:moderate",
                "advisor:low",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert parsed[0]["advisor:critical"] == 4
            assert parsed[0]["advisor:low"] == 1

    def test_inline_config_respects_sort(self, flask_app, db_create_host, inventory_config):
        captured, capture_post = _capture_posted_body()
        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            db_create_host(host=db_host(display_name="bbb"))
            db_create_host(host=db_host(display_name="aaa"))
            db_create_host(host=db_host(display_name="ccc"))

            assert _create_export(
                inventory_config,
                filters={
                    "configuration": {
                        "columns": [{"key": "display_name"}],
                        "sort": {"key": "display_name", "direction": "asc"},
                    }
                },
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )

            names = [row["display_name"] for row in json.loads(captured[0])]
            assert names == ["aaa", "bbb", "ccc"]

    def test_inline_config_sort_desc(self, flask_app, db_create_host, inventory_config):
        captured, capture_post = _capture_posted_body()
        with flask_app.app.app_context(), mock.patch("requests.Session.post", new=capture_post):
            db_create_host(host=db_host(display_name="bbb"))
            db_create_host(host=db_host(display_name="aaa"))
            db_create_host(host=db_host(display_name="ccc"))

            assert _create_export(
                inventory_config,
                filters={
                    "configuration": {
                        "columns": [{"key": "display_name"}],
                        "sort": {"key": "display_name", "direction": "desc"},
                    }
                },
                x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
            )

            names = [row["display_name"] for row in json.loads(captured[0])]
            assert names == ["ccc", "bbb", "aaa"]

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_invalid_column_returns_error(
        self, mock_handle_error, flask_app, db_create_host, inventory_config
    ):
        with flask_app.app.app_context():
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={"configuration": {"columns": [{"key": "not_a_real_column"}]}},
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 400

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_rejects_unauthorized_app_sort(
        self, mock_handle_error, flask_app, db_create_host, inventory_config
    ):
        with (
            flask_app.app.app_context(),
            mock.patch("app.queue.export_service.get_allowed_app_services", return_value={"advisor"}),
        ):
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={
                        "configuration": {
                            "columns": [{"key": "display_name"}],
                            "sort": {"key": "vulnerability:total_cves", "direction": "asc"},
                        }
                    },
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 403
            assert "Insufficient permissions to sort" in mock_handle_error.call_args[0][0]

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_empty_returns_error(self, mock_handle_error, flask_app, db_create_host, inventory_config):
        """A supplied-but-empty configuration must be rejected, not silently export legacy data."""
        with flask_app.app.app_context():
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={"configuration": {}},
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 400
            assert "columns" in mock_handle_error.call_args[0][0]

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_without_columns_returns_error(
        self, mock_handle_error, flask_app, db_create_host, inventory_config
    ):
        """A configuration carrying filters/sort but no columns must be rejected."""
        with flask_app.app.app_context():
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={"configuration": {"sort": {"key": "display_name", "direction": "asc"}}},
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 400

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_invalid_sort_direction_returns_error(
        self, mock_handle_error, flask_app, db_create_host, inventory_config
    ):
        """An unsupported sort direction must fail validation (400), not raise an unhandled
        ValueError that leaves the export stuck."""
        with flask_app.app.app_context():
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={
                        "configuration": {
                            "columns": [{"key": "display_name"}],
                            "sort": {"key": "display_name", "direction": "sideways"},
                        }
                    },
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 400
            assert "direction" in mock_handle_error.call_args[0][0]

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_unsupported_core_sort_key_returns_error(
        self, mock_handle_error, flask_app, db_create_host, inventory_config
    ):
        """Core keys that are valid as columns but unimplemented by params_to_order_by (e.g.
        "tags") must be rejected at validation, not raise an unhandled ValueError."""
        with flask_app.app.app_context():
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={
                        "configuration": {
                            "columns": [{"key": "display_name"}],
                            "sort": {"key": "tags", "direction": "asc"},
                        }
                    },
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 400
            assert "sort key" in mock_handle_error.call_args[0][0]

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_workspace_name_and_id_returns_error(
        self, mock_handle_error, flask_app, db_create_host, inventory_config
    ):
        """workspace_name and workspace_id resolve to the same group filters, which combine
        with AND semantics — two different workspaces would silently match nothing."""
        with flask_app.app.app_context():
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={
                        "configuration": {
                            "columns": [{"key": "display_name"}],
                            "filters": {
                                "host": {
                                    "workspace_name": ["my-group"],
                                    "workspace_id": ["5b58be21-39f5-4c11-9c61-6ce94f5dd274"],
                                }
                            },
                        }
                    },
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 400
            assert "mutually exclusive" in mock_handle_error.call_args[0][0]

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_invalid_workspace_id_returns_error(
        self, mock_handle_error, flask_app, db_create_host, inventory_config
    ):
        """A non-UUID workspace_id must fail validation (400), not reach the UUID-backed
        group_id database filter and fail the export."""
        with flask_app.app.app_context():
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={
                        "configuration": {
                            "columns": [{"key": "display_name"}],
                            "filters": {"host": {"workspace_id": ["not-a-uuid"]}},
                        }
                    },
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 400
            assert "not a valid workspace ID" in mock_handle_error.call_args[0][0]

    @mock.patch("app.queue.export_service._handle_export_error")
    def test_inline_config_workspace_id_wrong_type_returns_error(
        self, mock_handle_error, flask_app, db_create_host, inventory_config
    ):
        """Inline configurations are not schema-loaded, so a non-string workspace_id (e.g.
        an int) must be rejected at validation rather than break _group_ids_filter."""
        with flask_app.app.app_context():
            db_create_host()

            assert (
                _create_export(
                    inventory_config,
                    filters={
                        "configuration": {
                            "columns": [{"key": "display_name"}],
                            "filters": {"host": {"workspace_id": 123}},
                        }
                    },
                    x_rh_identity=es_utils.X_RH_IDENTITY_DEFAULT,
                )
                is False
            )
            mock_handle_error.assert_called_once()
            assert mock_handle_error.call_args[0][1] == 400
            assert "must be a workspace ID" in mock_handle_error.call_args[0][0]


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
                *ALWAYS_APPENDED_EXPORT_FIELDS,
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
                mapped = CORE_VIEW_FIELDS_TO_EXPORT_FIELDS.get(key) or COMPOSITE_VIEW_FIELDS_TO_EXPORT_FIELDS.get(key)
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
                "advisor:critical",
                "advisor:important",
                "advisor:moderate",
                "advisor:low",
                "vulnerability:critical_cves",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert app_data == {
                "advisor": ["critical", "important", "moderate", "low"],
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

            assert fields == [
                "host_id",
                "display_name",
                "advisor:critical",
                "advisor:important",
                "advisor:moderate",
                "advisor:low",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert app_data == {"advisor": ["critical", "important", "moderate", "low"]}

    def test_resolve_export_columns_allowed_apps_none_allows_all(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "display_name"},
                {"key": "advisor:recommendations"},
                {"key": "vulnerability:total_cves"},
            ]
            fields, app_data = resolve_export_columns(columns, allowed_apps=None)

            assert fields == [
                "host_id",
                "display_name",
                "advisor:critical",
                "advisor:important",
                "advisor:moderate",
                "advisor:low",
                "vulnerability:critical_cves",
                "vulnerability:important_cves",
                "vulnerability:moderate_cves",
                "vulnerability:low_cves",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert app_data == {
                "advisor": ["critical", "important", "moderate", "low"],
                "vulnerability": ["critical_cves", "important_cves", "moderate_cves", "low_cves"],
            }

    @pytest.mark.parametrize(
        "composite_key, expected_fields",
        [
            (
                "advisor:recommendations",
                ["advisor:critical", "advisor:important", "advisor:moderate", "advisor:low"],
            ),
            (
                "vulnerability:total_cves",
                [
                    "vulnerability:critical_cves",
                    "vulnerability:important_cves",
                    "vulnerability:moderate_cves",
                    "vulnerability:low_cves",
                ],
            ),
            (
                "patch:advisories_rhsa_installable",
                [
                    "patch:advisories_rhsa_installable",
                    "patch:advisories_rhba_installable",
                    "patch:advisories_rhea_installable",
                    "patch:advisories_other_installable",
                ],
            ),
        ],
    )
    def test_composite_columns_expand_into_individual_fields(self, flask_app, composite_key, expected_fields):
        """Composite UI columns export as their individual app-data fields instead of the combined value."""
        with flask_app.app.app_context():
            fields, app_data = resolve_export_columns([{"key": composite_key}])

            assert fields == ["host_id", *expected_fields, *ALWAYS_APPENDED_EXPORT_FIELDS]
            app_name = expected_fields[0].split(":", 1)[0]
            assert app_data == {app_name: [field.split(":", 1)[1] for field in expected_fields]}

    @pytest.mark.parametrize(
        "composite_key, expanded_fields",
        [
            (
                "advisor:recommendations",
                ["advisor:critical", "advisor:important", "advisor:moderate", "advisor:low"],
            ),
            (
                "vulnerability:total_cves",
                [
                    "vulnerability:critical_cves",
                    "vulnerability:important_cves",
                    "vulnerability:moderate_cves",
                    "vulnerability:low_cves",
                ],
            ),
            (
                "patch:advisories_rhsa_installable",
                [
                    "patch:advisories_rhsa_installable",
                    "patch:advisories_rhba_installable",
                    "patch:advisories_rhea_installable",
                    "patch:advisories_other_installable",
                ],
            ),
        ],
    )
    def test_hidden_composite_columns_are_omitted(self, flask_app, composite_key, expanded_fields):
        """A hidden composite column must not export the fields it expands into."""
        with flask_app.app.app_context():
            fields, app_data = resolve_export_columns(
                [
                    {"key": "display_name"},
                    {"key": composite_key, "shown": False},
                ]
            )

            assert fields == ["host_id", "display_name", *ALWAYS_APPENDED_EXPORT_FIELDS]
            assert app_data == {}
            assert not any(field in fields for field in expanded_fields)

    def test_composite_column_dropped_when_app_unauthorized(self, flask_app):
        with flask_app.app.app_context():
            fields, app_data = resolve_export_columns(
                [{"key": "display_name"}, {"key": "vulnerability:total_cves"}],
                allowed_apps={"advisor"},
            )

            assert fields == ["host_id", "display_name", *ALWAYS_APPENDED_EXPORT_FIELDS]
            assert app_data == {}

    def test_composite_expansion_deduplicates_overlapping_individual_columns(self, flask_app):
        with flask_app.app.app_context():
            columns = [
                {"key": "vulnerability:total_cves"},
                {"key": "vulnerability:critical_cves"},
            ]
            fields, app_data = resolve_export_columns(columns)

            assert fields == [
                "host_id",
                "vulnerability:critical_cves",
                "vulnerability:important_cves",
                "vulnerability:moderate_cves",
                "vulnerability:low_cves",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert app_data == {
                "vulnerability": ["critical_cves", "important_cves", "moderate_cves", "low_cves"],
            }

    def test_always_appended_export_fields_follow_selected_columns(self, flask_app):
        """WYSIWYG exports keep selected columns in order, then always append the
        export fields that no manage-columns entry can select."""
        with flask_app.app.app_context():
            columns = [{"key": "display_name"}, {"key": "operating_system"}]
            fields, _ = resolve_export_columns(columns)

            assert fields == [
                "host_id",
                "display_name",
                "os_release",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]

    def test_tag_columns_are_omitted(self, flask_app):
        with flask_app.app.app_context():
            fields, app_data = resolve_export_columns(
                [
                    {"key": "display_name"},
                    {"key": "tag:insights-client/env"},
                    {"key": "tag:owner", "shown": False},
                    {"key": "operating_system", "shown": False},
                ]
            )

            assert fields == [
                "host_id",
                "display_name",
                *ALWAYS_APPENDED_EXPORT_FIELDS,
            ]
            assert app_data == {}
            assert not any(field.startswith("tag:") for field in fields)

    def test_updated_view_column_not_duplicated_by_append(self, flask_app):
        """ "updated" is both a view field and an always-appended export field — it must
        appear exactly once, at its selected position."""
        with flask_app.app.app_context():
            fields, _ = resolve_export_columns([{"key": "updated"}])

            expected_appended = [f for f in ALWAYS_APPENDED_EXPORT_FIELDS if f != "updated"]
            assert fields == ["host_id", "updated", *expected_appended]

    def test_always_appended_export_fields_derived_from_legacy_export(self):
        """The append list is derived from the legacy export field set, so it can
        never drift from it — this pins the expected result of that derivation."""
        assert ALWAYS_APPENDED_EXPORT_FIELDS == [
            "fqdn",
            "subscription_manager_id",
            "satellite_id",
            "group_id",
            "updated",
            "host_type",
            "bios_uuid",
            "satellite_managed",
            "cloud_provider",
            "is_marketplace",
            "ip_addresses",
        ]


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

    def test_operating_system_sort_joins_static_profile_once(self, flask_app, db_create_host):
        """RHINENG-31802: sorting by operating_system must join the static profile table even
        when no static profile columns are exported, else the ORDER BY expression adds an
        unjoined FROM source that multiplies rows."""
        with flask_app.app.app_context():
            db_create_host(
                host=db_host(display_name="rhel-9"),
                extra_data={"system_profile_facts": {"operating_system": {"name": "RHEL", "major": 9, "minor": 1}}},
            )
            db_create_host(
                host=db_host(display_name="rhel-8"),
                extra_data={"system_profile_facts": {"operating_system": {"name": "RHEL", "major": 8, "minor": 5}}},
            )
            identity = Identity(USER_IDENTITY)

            with _capture_sql() as queries:
                results = list(
                    get_hosts_to_export(
                        identity,
                        export_fields=["host_id", "display_name"],
                        order_by="operating_system",
                        order_how="DESC",
                    )
                )

            # No row multiplication: each host appears exactly once (the bug would
            # Cartesian-product rows against an unjoined static profile table).
            names = [r["display_name"] for r in results]
            assert sorted(names) == ["rhel-8", "rhel-9"]
            static_queries = [q for q in queries if "system_profiles_static" in q]
            assert len(static_queries) == 1
            assert "LEFT OUTER JOIN" in static_queries[0].upper()

    def test_operating_system_sort_does_not_double_join_static_profile(self, flask_app, db_create_host):
        """When a static profile column is already exported, the operating_system sort must not
        join the table a second time."""
        with flask_app.app.app_context():
            db_create_host(extra_data={"system_profile_facts": _LEGACY_STATIC_PROFILE})
            identity = Identity(USER_IDENTITY)

            with _capture_sql() as queries:
                results = list(
                    get_hosts_to_export(
                        identity,
                        export_fields=["host_id", "os_release"],
                        order_by="operating_system",
                        order_how="ASC",
                    )
                )

            assert len(results) == 1
            static_queries = [q for q in queries if "system_profiles_static" in q]
            assert len(static_queries) == 1
            assert static_queries[0].upper().count("JOIN HBI.SYSTEM_PROFILES_STATIC") <= 1

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

    def test_content_host_filter_joins_patch_and_matches_only_that_host(
        self, flask_app, db_create_host, db_create_host_app_data
    ):
        """Content filters must LEFT JOIN patch. An unjoined table cross-matches other hosts."""
        with flask_app.app.app_context():
            security = db_create_host(host=db_host(display_name="security-present"))
            bugfix = db_create_host(host=db_host(display_name="bugfix-absent"))
            db_create_host(host=db_host(display_name="no-patch-row"))
            db_create_host_app_data(
                str(security.id),
                "test",
                "patch",
                advisories_rhsa_installable=2,
                advisories_rhba_installable=0,
                advisories_rhea_installable=0,
                advisories_other_installable=0,
                template_uuid=uuid4(),
            )
            db_create_host_app_data(
                str(bugfix.id),
                "test",
                "patch",
                advisories_rhsa_installable=0,
                advisories_rhba_installable=3,
                advisories_rhea_installable=0,
                advisories_other_installable=0,
                template_uuid=None,
            )
            identity = Identity(USER_IDENTITY)

            cases = [
                ({"installable_advisory_type": ["security"]}, ["security-present"]),
                ({"installable_advisory_type": ["not_evaluated"]}, ["no-patch-row"]),
                ({"template": "present"}, ["security-present"]),
                ({"template": "not_present"}, ["bugfix-absent"]),
                (
                    {"installable_advisory_type": ["security"], "template": "present"},
                    ["security-present"],
                ),
            ]
            for host_filter, expected in cases:
                with _capture_sql() as queries:
                    results = list(
                        get_hosts_to_export(
                            identity,
                            export_fields=["host_id", "display_name"],
                            host_filter=host_filter,
                        )
                    )

                assert sorted(r["display_name"] for r in results) == expected
                joined = [q for q in queries if "LEFT OUTER JOIN" in q.upper() and "hosts_app_data_patch" in q]
                assert len(joined) == 1

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
