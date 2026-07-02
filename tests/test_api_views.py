import uuid
from copy import deepcopy

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_views_url
from tests.helpers.api_utils import do_request
from tests.helpers.test_utils import USER_IDENTITY

SYSTEM_TYPE_IDENTITY = deepcopy(USER_IDENTITY)
SYSTEM_TYPE_IDENTITY["type"] = "System"
SYSTEM_TYPE_IDENTITY.pop("user", None)
SYSTEM_TYPE_IDENTITY["system"] = {"cert_type": "system", "cn": "test-cn"}

USERNAME = USER_IDENTITY["user"]["username"]


class TestGetViewsList:
    def test_returns_empty_list(self, flask_client):
        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 0
        assert response_data["results"] == []

    def test_returns_own_private_view(self, flask_client, db_create_view):
        db_create_view(name="My View", org_id=USER_IDENTITY["org_id"], created_by=USERNAME)

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["name"] == "My View"
        assert response_data["results"][0]["is_owner"] is True

    def test_returns_org_wide_view(self, flask_client, db_create_view):
        db_create_view(
            name="Shared View",
            org_id=USER_IDENTITY["org_id"],
            created_by="someone_else@redhat.com",
            org_wide=True,
        )

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["name"] == "Shared View"
        assert response_data["results"][0]["is_owner"] is False

    def test_returns_system_view(self, flask_client, db_create_system_view):
        db_create_system_view(name="Red Hat Default")

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 1
        assert response_data["results"][0]["name"] == "Red Hat Default"
        assert response_data["results"][0]["is_system_view"] is True

    def test_excludes_other_users_private_view(self, flask_client, db_create_view):
        db_create_view(
            name="Secret View",
            org_id=USER_IDENTITY["org_id"],
            created_by="someone_else@redhat.com",
            org_wide=False,
        )

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 0

    def test_excludes_other_org_view(self, flask_client, db_create_view):
        db_create_view(name="Other Org", org_id="other-org", created_by="other@redhat.com", org_wide=True)

        url = build_views_url()
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 0

    def test_pagination(self, flask_client, db_create_view):
        for i in range(5):
            db_create_view(name=f"View {i}", org_id=USER_IDENTITY["org_id"], created_by=USERNAME)

        url = build_views_url(query="?per_page=2&page=1")
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["total"] == 5
        assert response_data["count"] == 2
        assert response_data["page"] == 1
        assert response_data["per_page"] == 2

    def test_403_for_unsupported_identity_type(self, flask_client):
        url = build_views_url()
        response_status, _ = do_request(flask_client.get, url, SYSTEM_TYPE_IDENTITY)

        assert_response_status(response_status, 403)


class TestGetViewById:
    def test_returns_own_view(self, flask_client, db_create_view):
        view = db_create_view(name="Detail View", org_id=USER_IDENTITY["org_id"], created_by=USERNAME)

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["name"] == "Detail View"
        assert response_data["id"] == str(view.id)
        assert response_data["is_owner"] is True

    def test_returns_system_view(self, flask_client, db_create_system_view):
        view = db_create_system_view(name="System Detail")

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["is_system_view"] is True

    def test_returns_org_wide_view_for_same_org(self, flask_client, db_create_view):
        view = db_create_view(
            name="Shared",
            org_id=USER_IDENTITY["org_id"],
            created_by="someone_else@redhat.com",
            org_wide=True,
        )

        url = build_views_url(view_id=str(view.id))
        response_status, response_data = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 200)
        assert response_data["is_owner"] is False

    def test_404_for_nonexistent_view(self, flask_client):
        url = build_views_url(view_id=str(uuid.uuid4()))
        response_status, _ = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_404_for_other_users_private_view(self, flask_client, db_create_view):
        view = db_create_view(
            org_id=USER_IDENTITY["org_id"],
            created_by="someone_else@redhat.com",
            org_wide=False,
        )

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_404_for_other_org_view(self, flask_client, db_create_view):
        view = db_create_view(org_id="other-org", created_by="other@redhat.com", org_wide=True)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.get, url, USER_IDENTITY)

        assert_response_status(response_status, 404)

    def test_403_for_unsupported_identity_type(self, flask_client, db_create_view):
        view = db_create_view(org_id=USER_IDENTITY["org_id"], created_by=USERNAME)

        url = build_views_url(view_id=str(view.id))
        response_status, _ = do_request(flask_client.get, url, SYSTEM_TYPE_IDENTITY)

        assert_response_status(response_status, 403)
