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

    def test_400_for_unknown_visible_field(self, flask_client: TestClient) -> None:
        data = {"name": "Bad", "configuration": {"columns": [{"key": "display_name", "visible": True}]}}

        url = build_views_url()
        response_status, response_data = do_request(flask_client.post, url, USER_IDENTITY, data)

        assert_response_status(response_status, 400)
        assert "visible" in response_data["detail"]

    def test_403_for_unsupported_identity_type(self, flask_client: TestClient) -> None:
        data = {"name": "Test", "configuration": VALID_CONFIG}

        url = build_views_url()
        response_status, _ = do_request(flask_client.post, url, SYSTEM_TYPE_IDENTITY, data)

        assert_response_status(response_status, 403)
