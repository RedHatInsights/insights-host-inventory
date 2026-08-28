import uuid
from collections.abc import Callable
from copy import deepcopy

from starlette.testclient import TestClient

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_views_url
from tests.helpers.api_utils import do_request
from tests.helpers.test_utils import USER_IDENTITY

SYSTEM_TYPE_IDENTITY = deepcopy(USER_IDENTITY)
SYSTEM_TYPE_IDENTITY["type"] = "System"
SYSTEM_TYPE_IDENTITY.pop("user", None)
SYSTEM_TYPE_IDENTITY["system"] = {"cert_type": "system", "cn": "test-cn"}

USER_ID = USER_IDENTITY["user"]["user_id"]

VALID_CONFIG = {"columns": [{"key": "display_name"}]}


class TestGetViewsList:
    def test_returns_empty_list(self, flask_client: TestClient) -> None:
        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 0
        assert response_data["results"] == []

    def test_returns_own_private_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        db_create_view(name="My View", org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["name"] == "My View"
        assert response_data["results"][0]["is_owner"] is True

    def test_returns_org_wide_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        db_create_view(
            name="Shared View",
            org_id=USER_IDENTITY["org_id"],
            created_by="98765432",
            org_wide=True,
        )

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["name"] == "Shared View"
        assert response_data["results"][0]["is_owner"] is False

    def test_returns_system_view(self, flask_client: TestClient, db_create_system_view: Callable) -> None:
        db_create_system_view(name="Red Hat Default")

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["name"] == "Red Hat Default"
        assert response_data["results"][0]["is_system_view"] is True

    def test_excludes_other_users_private_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        db_create_view(
            name="Secret View",
            org_id=USER_IDENTITY["org_id"],
            created_by="98765432",
            org_wide=False,
        )

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 0

    def test_excludes_other_org_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        db_create_view(name="Other Org", org_id="other-org", created_by="other-user-id", org_wide=True)

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 0

    def test_pagination(self, flask_client: TestClient, db_create_view: Callable) -> None:
        for i in range(5):
            db_create_view(name=f"View {i}", org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(query="?per_page=2&page=1")
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 5
        assert response_data["count"] == 2
        assert response_data["page"] == 1
        assert response_data["per_page"] == 2

    def test_403_for_unsupported_identity_type(self, flask_client: TestClient) -> None:
        url = build_views_url()
        response_status, _ = do_request(flask_client.get, url, SYSTEM_TYPE_IDENTITY)

        assert_response_status(response_status, 403)


class TestGetViewById:
    def test_returns_own_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(name="Detail View", org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["name"] == "Detail View"
        assert response_data["id"] == str(view.id)
        assert response_data["is_owner"] is True

    def test_returns_system_view(self, flask_client: TestClient, db_create_system_view: Callable) -> None:
        view = db_create_system_view(name="System Detail")

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["is_system_view"] is True

    def test_returns_org_wide_view_for_same_org(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(
            name="Shared",
            org_id=USER_IDENTITY["org_id"],
            created_by="98765432",
            org_wide=True,
        )

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["is_owner"] is False

    def test_404_for_nonexistent_view(self, flask_client: TestClient) -> None:
        url = build_views_url(view_id=str(uuid.uuid4()))
        response_status, _ = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_404_for_other_users_private_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(
            org_id=USER_IDENTITY["org_id"],
            created_by="98765432",
            org_wide=False,
        )

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_404_for_other_org_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id="other-org", created_by="other-user-id", org_wide=True)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_403_for_unsupported_identity_type(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.get, url, SYSTEM_TYPE_IDENTITY)

        assert_response_status(response_status, 403)


class TestCreateView:
    def test_creates_view(self, flask_client: TestClient) -> None:
        data = {"name": "New View", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["name"] == "New View"
        assert response_data["org_id"] == USER_IDENTITY["org_id"]
        assert response_data["created_by"] == USER_ID
        assert response_data["is_owner"] is True
        assert response_data["is_system_view"] is False
        assert response_data["org_wide"] is False

    def test_creates_org_wide_view(self, flask_client: TestClient) -> None:
        data = {"name": "Shared View", "configuration": VALID_CONFIG, "org_wide": True}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["org_wide"] is True

    def test_creates_view_with_description(self, flask_client: TestClient) -> None:
        data = {"name": "Described", "configuration": VALID_CONFIG, "description": "A test view"}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["description"] == "A test view"

    def test_creates_view_with_app_field_columns(self, flask_client: TestClient) -> None:
        config = {
            "columns": [
                {"key": "display_name"},
                {"key": "vulnerability:critical_cves"},
                {"key": "advisor:recommendations"},
                {"key": "compliance:last_scan"},
            ]
        }
        data = {"name": "Security View", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert len(response_data["configuration"]["columns"]) == 4

    def test_creates_view_with_all_core_columns(self, flask_client: TestClient) -> None:
        config = {
            "columns": [
                {"key": "display_name"},
                {"key": "group_name"},
                {"key": "operating_system"},
                {"key": "updated"},
                {"key": "last_check_in"},
                {"key": "per_reporter_staleness"},
                {"key": "tags"},
                {"key": "status"},
                {"key": "infrastructure"},
                {"key": "vendor"},
                {"key": "workload"},
                {"key": "created"},
            ]
        }
        data = {"name": "All Core Columns View", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert len(response_data["configuration"]["columns"]) == 12

    def test_creates_view_with_sort(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "sort": {"key": "vulnerability:critical_cves", "direction": "desc"},
        }
        data = {"name": "Sorted View", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["configuration"]["sort"]["key"] == "vulnerability:critical_cves"

    def test_creates_view_with_filters(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "vulnerability": {"critical_cves": {"gte": "1"}},
            },
        }
        data = {"name": "Filtered View", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["configuration"]["filters"]["vulnerability"]["critical_cves"]["gte"] == "1"

    def test_creates_view_with_system_profile_os_filter(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "system_profile": {
                    "operating_system": {"RHEL": {"version": {"eq": ["9.6"]}}},
                },
            },
        }
        data = {"name": "RHEL 96 View OS Filter", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["configuration"]["filters"]["system_profile"]["operating_system"] == {
            "RHEL": {"version": {"eq": ["9.6"]}}
        }

    def test_creates_view_with_system_profile_host_type_filter(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "system_profile": {"host_type": {"eq": "edge"}},
            },
        }
        data = {"name": "Edge Hosts", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["configuration"]["filters"]["system_profile"]["host_type"]["eq"] == "edge"

    def test_creates_view_with_combined_system_profile_and_app_filters(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}, {"key": "operating_system"}],
            "filters": {
                "system_profile": {
                    "operating_system": {"RHEL": {"version": {"eq": ["9.0"]}}},
                },
                "vulnerability": {"critical_cves": {"gte": "1"}},
            },
        }
        data = {"name": "Vuln RHEL Hosts", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        filters = response_data["configuration"]["filters"]
        assert filters["system_profile"]["operating_system"] == {"RHEL": {"version": {"eq": ["9.0"]}}}
        assert filters["vulnerability"]["critical_cves"]["gte"] == "1"

    def test_creates_view_with_host_filters(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "host": {
                    "hostname_or_id": "web-server",
                    "staleness": ["fresh", "stale"],
                    "registered_with": ["insights"],
                    "tags": ["namespace/key=value"],
                    "workspace_name": ["production"],
                    "system_type": ["edge"],
                },
            },
        }
        data = {"name": "Host Filtered View", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        hf = response_data["configuration"]["filters"]["host"]
        assert hf["hostname_or_id"] == "web-server"
        assert hf["staleness"] == ["fresh", "stale"]
        assert hf["registered_with"] == ["insights"]
        assert hf["tags"] == ["namespace/key=value"]
        assert hf["workspace_name"] == ["production"]
        assert hf["system_type"] == ["edge"]

    def test_creates_view_with_host_filters_date_ranges(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "host": {
                    "last_check_in_start": "2025-01-01T00:00:00+00:00",
                    "last_check_in_end": "2025-06-01T00:00:00+00:00",
                    "updated_start": "2025-03-01T00:00:00+00:00",
                    "updated_end": "2025-06-01T00:00:00+00:00",
                },
            },
        }
        data = {"name": "Date Range View", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        hf = response_data["configuration"]["filters"]["host"]
        assert hf["last_check_in_start"] == "2025-01-01T00:00:00+00:00"
        assert hf["last_check_in_end"] == "2025-06-01T00:00:00+00:00"
        assert hf["updated_start"] == "2025-03-01T00:00:00+00:00"
        assert hf["updated_end"] == "2025-06-01T00:00:00+00:00"

    def test_creates_view_with_combined_filters_and_host_filters(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "vulnerability": {"critical_cves": {"gte": "1"}},
                "host": {
                    "staleness": ["fresh"],
                    "hostname_or_id": "prod",
                },
            },
        }
        data = {"name": "Combined Filters", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["configuration"]["filters"]["vulnerability"]["critical_cves"]["gte"] == "1"
        assert response_data["configuration"]["filters"]["host"]["staleness"] == ["fresh"]
        assert response_data["configuration"]["filters"]["host"]["hostname_or_id"] == "prod"

    def test_400_for_invalid_staleness_in_host_filters(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {"host": {"staleness": ["invalid_state"]}},
        }
        data = {"name": "Bad Staleness", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "invalid_state" in response_data["detail"]

    def test_400_for_unknown_host_filter_key(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {"host": {"nonexistent_param": "value"}},
        }
        data = {"name": "Bad Host Filter", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "nonexistent_param" in response_data["detail"]

    def test_400_for_inverted_last_check_in_range_in_host_filters(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "host": {
                    "last_check_in_start": "2025-06-01T00:00:00+00:00",
                    "last_check_in_end": "2025-01-01T00:00:00+00:00",
                }
            },
        }
        data = {"name": "Bad Date Range", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "last_check_in_start" in response_data["detail"]

    def test_400_for_inverted_updated_range_in_host_filters(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "host": {
                    "updated_start": "2025-12-01T00:00:00+00:00",
                    "updated_end": "2025-01-01T00:00:00+00:00",
                }
            },
        }
        data = {"name": "Bad Updated Range", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "updated_start" in response_data["detail"]

    def test_400_for_invalid_iso_datetime_in_host_filters(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {"host": {"last_check_in_start": "not-a-date"}},
        }
        data = {"name": "Invalid Datetime", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "last_check_in_start" in response_data["detail"]

    def test_created_view_appears_in_list(self, flask_client: TestClient) -> None:
        data = {"name": "Listed View", "configuration": VALID_CONFIG}

        url = build_views_url()
        do_request(flask_client.post, url, USER_IDENTITY, data)

        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["name"] == "Listed View"

    def test_400_for_missing_name(self, flask_client: TestClient) -> None:
        data = {"configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_400_for_missing_configuration(self, flask_client: TestClient) -> None:
        data = {"name": "No Config"}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "configuration" in response_data["detail"]

    def test_400_for_empty_name(self, flask_client: TestClient) -> None:
        data = {"name": "", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_400_for_whitespace_only_name(self, flask_client: TestClient) -> None:
        data = {"name": "   ", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_400_for_invalid_columns_type(self, flask_client: TestClient) -> None:
        data = {"name": "Bad Config", "configuration": {"columns": "not-a-list"}}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "columns" in response_data["detail"]

    def test_400_for_missing_column_key(self, flask_client: TestClient) -> None:
        data = {"name": "Bad Config", "configuration": {"columns": [{}]}}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "key" in response_data["detail"]

    def test_400_for_invalid_column_key(self, flask_client: TestClient) -> None:
        data = {"name": "Bad Key", "configuration": {"columns": [{"key": "nonexistent_field"}]}}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "nonexistent_field" in response_data["detail"]

    def test_400_for_invalid_app_column_key(self, flask_client: TestClient) -> None:
        data = {
            "name": "Bad App Key",
            "configuration": {"columns": [{"key": "advisor:nonexistent"}]},
        }

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "advisor:nonexistent" in response_data["detail"]

    def test_400_for_invalid_sort_key(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "sort": {"key": "invalid:field", "direction": "asc"},
        }
        data = {"name": "Bad Sort", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "invalid:field" in response_data["detail"]

    def test_400_for_invalid_filter_namespace(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {"nonexistent_app": {"field": {"eq": "value"}}},
        }
        data = {"name": "Bad Filter", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "nonexistent_app" in response_data["detail"]

    def test_400_for_invalid_filter_field(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {"vulnerability": {"nonexistent_field": {"eq": "1"}}},
        }
        data = {"name": "Bad Filter Field", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "nonexistent_field" in response_data["detail"]

    def test_400_for_invalid_filter_operator(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {"vulnerability": {"critical_cves": {"invalid_op": "1"}}},
        }
        data = {"name": "Bad Operator", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "invalid_op" in response_data["detail"]

    def test_400_for_invalid_system_profile_os_name(self, flask_client: TestClient) -> None:
        config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "system_profile": {
                    "operating_system": {"INVALID_OS": {"version": {"eq": ["9.6"]}}},
                },
            },
        }
        data = {"name": "Bad OS Name", "configuration": config}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "operating_system" in response_data["detail"]

    def test_400_for_unknown_visible_field(self, flask_client: TestClient) -> None:
        data = {"name": "Bad", "configuration": {"columns": [{"key": "display_name", "visible": True}]}}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "visible" in response_data["detail"]

    def test_400_for_special_characters_in_name(self, flask_client: TestClient) -> None:
        data = {"name": "Bad@Name!", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_400_for_control_characters_in_name(self, flask_client: TestClient) -> None:
        data = {"name": "Bad\nName", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_400_for_punctuation_only_name(self, flask_client: TestClient) -> None:
        data = {"name": "!!!", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_creates_view_with_hyphens_and_underscores(self, flask_client: TestClient) -> None:
        data = {"name": "my-view_2024", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 201)
        assert response_data["name"] == "my-view_2024"

    def test_403_for_unsupported_identity_type(self, flask_client: TestClient) -> None:
        data = {"name": "Test", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, _ = do_request(flask_client.post, url, SYSTEM_TYPE_IDENTITY, data)

        assert_response_status(response_status, 403)


class TestUpdateView:
    def test_updates_name(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(name="Old Name", org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.patch, url, USER_IDENTITY, {"name": "New Name"})

        assert_response_status(response_status, 200)
        assert response_data["name"] == "New Name"
        assert response_data["id"] == str(view.id)
        assert response_data["created_by"] == USER_ID
        assert response_data["org_id"] == USER_IDENTITY["org_id"]
        assert response_data["org_wide"] is False

    def test_updates_description(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(
            flask_client.patch, url, USER_IDENTITY, {"description": "Updated desc"}
        )

        assert_response_status(response_status, 200)
        assert response_data["description"] == "Updated desc"

    def test_updates_configuration(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)
        new_config = {"columns": [{"key": "display_name"}, {"key": "vulnerability:critical_cves"}]}

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(
            flask_client.patch, url, USER_IDENTITY, {"configuration": new_config}
        )

        assert_response_status(response_status, 200)
        assert response_data["configuration"]["columns"] == [
            {"key": "display_name"},
            {"key": "vulnerability:critical_cves"},
        ]

    def test_updates_org_wide(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID, org_wide=False)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.patch, url, USER_IDENTITY, {"org_wide": True})

        assert_response_status(response_status, 200)
        assert response_data["org_wide"] is True

    def test_updates_multiple_fields(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(
            flask_client.patch, url, USER_IDENTITY, {"name": "Updated", "description": "New desc", "org_wide": True}
        )

        assert_response_status(response_status, 200)
        assert response_data["name"] == "Updated"
        assert response_data["description"] == "New desc"
        assert response_data["org_wide"] is True

    def test_updates_configuration_with_host_filters(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        new_config = {
            "columns": [{"key": "display_name"}],
            "filters": {
                "host": {
                    "staleness": ["fresh"],
                    "hostname_or_id": "db-server",
                }
            },
        }
        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(
            flask_client.patch, url, USER_IDENTITY, {"configuration": new_config}
        )

        assert_response_status(response_status, 200)
        hf = response_data["configuration"]["filters"]["host"]
        assert hf["staleness"] == ["fresh"]
        assert hf["hostname_or_id"] == "db-server"

    def test_400_for_invalid_host_filters_on_update(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        bad_config = {
            "columns": [{"key": "display_name"}],
            "filters": {"host": {"staleness": ["rotten"]}},
        }
        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(
            flask_client.patch, url, USER_IDENTITY, {"configuration": bad_config}
        )

        assert_response_status(response_status, 400)
        assert "rotten" in response_data["detail"]

    def test_400_for_unknown_host_filter_key_on_update(
        self, flask_client: TestClient, db_create_view: Callable
    ) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        bad_config = {
            "columns": [{"key": "display_name"}],
            "filters": {"host": {"nonexistent_param": "value"}},
        }
        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(
            flask_client.patch, url, USER_IDENTITY, {"configuration": bad_config}
        )

        assert_response_status(response_status, 400)
        assert "nonexistent_param" in response_data["detail"]

    def test_400_for_invalid_column_key(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(
            flask_client.patch, url, USER_IDENTITY, {"configuration": {"columns": [{"key": "fake_field"}]}}
        )

        assert_response_status(response_status, 400)
        assert "fake_field" in response_data["detail"]

    def test_400_for_empty_body(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.patch, url, USER_IDENTITY, {})

        assert_response_status(response_status, 400)
        assert "at least one field" in response_data["detail"]

    def test_400_for_empty_name(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.patch, url, USER_IDENTITY, {"name": ""})

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_400_for_special_characters_in_name(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.patch, url, USER_IDENTITY, {"name": "New@Name!"})

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_400_for_control_characters_in_name(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.patch, url, USER_IDENTITY, {"name": "Bad\nName"})

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_400_for_punctuation_only_name(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.patch, url, USER_IDENTITY, {"name": "!!!"})

        assert_response_status(response_status, 400)
        assert "name" in response_data["detail"]

    def test_updates_name_with_hyphens_and_underscores(
        self, flask_client: TestClient, db_create_view: Callable
    ) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.patch, url, USER_IDENTITY, {"name": "my-view_2024"})

        assert_response_status(response_status, 200)
        assert response_data["name"] == "my-view_2024"

    def test_403_for_system_view(self, flask_client: TestClient, db_create_system_view: Callable) -> None:
        view = db_create_system_view()

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.patch, url, USER_IDENTITY, {"name": "Hacked"})

        assert_response_status(response_status, 403)

    def test_403_for_non_owner(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by="98765432", org_wide=True)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.patch, url, USER_IDENTITY, {"name": "Hacked"})

        assert_response_status(response_status, 403)

    def test_404_for_nonexistent_view(self, flask_client: TestClient) -> None:
        url = build_views_url(view_id=str(uuid.uuid4()))
        response_status, _ = do_request(flask_client.patch, url, USER_IDENTITY, {"name": "X"})

        assert_response_status(response_status, 404)

    def test_403_for_unsupported_identity_type(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.patch, url, SYSTEM_TYPE_IDENTITY, {"name": "X"})

        assert_response_status(response_status, 403)


class TestDeleteView:
    def test_deletes_own_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.delete, url, USER_IDENTITY)

        assert_response_status(response_status, 204)

        # Verify it's gone
        response_status, _ = do_request(flask_client.get, url, USER_IDENTITY)
        assert_response_status(response_status, 404)

    def test_403_for_system_view(self, flask_client: TestClient, db_create_system_view: Callable) -> None:
        view = db_create_system_view()

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.delete, url, USER_IDENTITY)

        assert_response_status(response_status, 403)

    def test_403_for_non_owner(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by="98765432", org_wide=True)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.delete, url, USER_IDENTITY)

        assert_response_status(response_status, 403)

    def test_404_for_nonexistent_view(self, flask_client: TestClient) -> None:
        url = build_views_url(view_id=str(uuid.uuid4()))
        response_status, _ = do_request(flask_client.delete, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_403_for_unsupported_identity_type(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.delete, url, SYSTEM_TYPE_IDENTITY)

        assert_response_status(response_status, 403)


class TestCloneView:
    def test_clones_own_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(name="Original", org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id), clone=True)
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY)

        assert_response_status(response_status, 201)
        assert response_data["name"] == "Copy of Original"
        assert response_data["id"] != str(view.id)
        assert response_data["is_owner"] is True
        assert response_data["org_wide"] is False
        assert response_data["is_system_view"] is False
        assert response_data["created_by"] == USER_ID

    def test_clones_system_view(self, flask_client: TestClient, db_create_system_view: Callable) -> None:
        view = db_create_system_view(name="Red Hat Default")

        url = build_views_url(view_id=str(view.id), clone=True)
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY)

        assert_response_status(response_status, 201)
        assert response_data["name"] == "Copy of Red Hat Default"
        assert response_data["is_system_view"] is False
        assert response_data["org_id"] == USER_IDENTITY["org_id"]

    def test_clones_org_wide_view_from_other_user(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(
            name="Shared View",
            org_id=USER_IDENTITY["org_id"],
            created_by="98765432",
            org_wide=True,
        )

        url = build_views_url(view_id=str(view.id), clone=True)
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY)

        assert_response_status(response_status, 201)
        assert response_data["created_by"] == USER_ID
        assert response_data["org_wide"] is False

    def test_clone_preserves_configuration(self, flask_client: TestClient, db_create_view: Callable) -> None:
        config = {
            "columns": [{"key": "display_name"}, {"key": "vulnerability:critical_cves"}],
            "sort": {"key": "display_name", "direction": "asc"},
        }
        view = db_create_view(
            name="Configured",
            org_id=USER_IDENTITY["org_id"],
            created_by=USER_ID,
            configuration=config,
        )

        url = build_views_url(view_id=str(view.id), clone=True)
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY)

        assert_response_status(response_status, 201)
        assert response_data["configuration"] == config

    def test_clone_truncates_long_name(self, flask_client: TestClient, db_create_view: Callable) -> None:
        from app.models.views import MAX_VIEW_NAME_LENGTH

        long_name = "A" * MAX_VIEW_NAME_LENGTH
        view = db_create_view(name=long_name, org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id), clone=True)
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY)

        assert_response_status(response_status, 201)
        assert len(response_data["name"]) == MAX_VIEW_NAME_LENGTH
        assert response_data["name"].startswith("Copy of ")

    def test_404_for_nonexistent_view(self, flask_client: TestClient) -> None:
        url = build_views_url(view_id=str(uuid.uuid4()), clone=True)
        response_status, _ = do_request(flask_client.post, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_404_for_other_users_private_view(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(
            org_id=USER_IDENTITY["org_id"],
            created_by="98765432",
            org_wide=False,
        )

        url = build_views_url(view_id=str(view.id), clone=True)
        response_status, _ = do_request(flask_client.post, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_403_for_unsupported_identity_type(self, flask_client: TestClient, db_create_view: Callable) -> None:
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USER_ID)

        url = build_views_url(view_id=str(view.id), clone=True)
        response_status, _ = do_request(flask_client.post, url, SYSTEM_TYPE_IDENTITY)

        assert_response_status(response_status, 403)
