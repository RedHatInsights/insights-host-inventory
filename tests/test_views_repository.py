import uuid

import pytest

from app.models import InventoryView
from app.models import db
from app.serialization import serialize_view
from lib.views_repository import CLONE_NAME_PREFIX
from lib.views_repository import ViewNotFoundError
from lib.views_repository import ViewPermissionError
from lib.views_repository import clone_view
from lib.views_repository import create_view
from lib.views_repository import delete_view
from lib.views_repository import get_view_by_id
from lib.views_repository import get_views_list
from lib.views_repository import update_view

ORG_ID = "test-org-1"
OTHER_ORG = "test-org-2"
USERNAME = "testuser"
OTHER_USER = "otheruser"

VALID_CONFIG = {"columns": [{"key": "display_name", "visible": True}]}


class TestGetViewsList:
    def test_returns_own_private_views(self, db_create_view):
        db_create_view(name="My Private View", org_id=ORG_ID, created_by=USERNAME, org_wide=False)

        views, total = get_views_list(ORG_ID, USERNAME)

        assert total == 1
        assert views[0].name == "My Private View"

    def test_returns_org_wide_views(self, db_create_view):
        db_create_view(name="Shared View", org_id=ORG_ID, created_by=OTHER_USER, org_wide=True)

        views, total = get_views_list(ORG_ID, USERNAME)

        assert total == 1
        assert views[0].name == "Shared View"

    def test_returns_system_views(self, db_create_system_view):
        db_create_system_view(name="System Default")

        views, total = get_views_list(ORG_ID, USERNAME)

        assert total == 1
        assert views[0].name == "System Default"
        assert views[0].is_system_view is True

    def test_excludes_other_users_private_views(self, db_create_view):
        db_create_view(name="Other Private", org_id=ORG_ID, created_by=OTHER_USER, org_wide=False)

        views, total = get_views_list(ORG_ID, USERNAME)

        assert total == 0
        assert views == []

    def test_excludes_other_org_views(self, db_create_view):
        db_create_view(name="Other Org View", org_id=OTHER_ORG, created_by=OTHER_USER, org_wide=True)

        views, total = get_views_list(ORG_ID, USERNAME)

        assert total == 0

    def test_pagination(self, db_create_view):
        for i in range(5):
            db_create_view(name=f"View {i}", org_id=ORG_ID, created_by=USERNAME)

        views, total = get_views_list(ORG_ID, USERNAME, page=1, per_page=2)

        assert total == 5
        assert len(views) == 2

    def test_ordered_by_modified_on_desc(self, db_create_view):
        v1 = db_create_view(name="Old View", org_id=ORG_ID, created_by=USERNAME)
        v2 = db_create_view(name="New View", org_id=ORG_ID, created_by=USERNAME)

        views, _ = get_views_list(ORG_ID, USERNAME)

        assert views[0].id == v2.id
        assert views[1].id == v1.id

    def test_is_owner_via_serialization(self, db_create_view):
        db_create_view(name="Mine", org_id=ORG_ID, created_by=USERNAME, org_wide=True)
        db_create_view(name="Theirs", org_id=ORG_ID, created_by=OTHER_USER, org_wide=True)

        views, _ = get_views_list(ORG_ID, USERNAME)

        by_name = {v.name: serialize_view(v, USERNAME) for v in views}
        assert by_name["Mine"]["is_owner"] is True
        assert by_name["Theirs"]["is_owner"] is False


class TestGetViewById:
    def test_returns_visible_view(self, db_create_view):
        view = db_create_view(name="My View", org_id=ORG_ID, created_by=USERNAME)

        result = get_view_by_id(str(view.id), ORG_ID, USERNAME)

        assert result.name == "My View"
        assert result.id == view.id

    def test_returns_system_view(self, db_create_system_view):
        view = db_create_system_view()

        result = get_view_by_id(str(view.id), ORG_ID, USERNAME)

        assert result.is_system_view is True

    def test_raises_for_nonexistent_view(self, flask_app):  # noqa: ARG002
        with pytest.raises(ViewNotFoundError):
            get_view_by_id(str(uuid.uuid4()), ORG_ID, USERNAME)

    def test_raises_for_other_users_private_view(self, db_create_view):
        view = db_create_view(org_id=ORG_ID, created_by=OTHER_USER, org_wide=False)

        with pytest.raises(ViewNotFoundError):
            get_view_by_id(str(view.id), ORG_ID, USERNAME)


class TestCreateView:
    def test_creates_view(self, flask_app):  # noqa: ARG002
        data = {"name": "New View", "configuration": VALID_CONFIG}

        result = create_view(data, ORG_ID, USERNAME)

        assert result.name == "New View"
        assert result.org_id == ORG_ID
        assert result.created_by == USERNAME
        assert result.org_wide is False

    def test_creates_org_wide_view(self, flask_app):  # noqa: ARG002
        data = {"name": "Shared", "configuration": VALID_CONFIG, "org_wide": True}

        result = create_view(data, ORG_ID, USERNAME)

        assert result.org_wide is True

    def test_ignores_client_provided_identity_fields(self, flask_app):  # noqa: ARG002
        data = {
            "name": "Sneaky",
            "configuration": VALID_CONFIG,
            "org_id": OTHER_ORG,
            "created_by": OTHER_USER,
        }

        result = create_view(data, ORG_ID, USERNAME)

        assert result.org_id == ORG_ID
        assert result.created_by == USERNAME

    def test_creates_view_with_description(self, flask_app):  # noqa: ARG002
        data = {"name": "Described", "configuration": VALID_CONFIG, "description": "A test view"}

        result = create_view(data, ORG_ID, USERNAME)

        assert result.description == "A test view"


class TestUpdateView:
    def test_updates_name(self, db_create_view):
        view = db_create_view(name="Old Name", org_id=ORG_ID, created_by=USERNAME)

        result = update_view(str(view.id), {"name": "New Name"}, ORG_ID, USERNAME)

        assert result.name == "New Name"

    def test_updates_multiple_fields(self, db_create_view):
        view = db_create_view(org_id=ORG_ID, created_by=USERNAME)

        result = update_view(
            str(view.id),
            {"name": "Updated", "description": "New desc", "org_wide": True},
            ORG_ID,
            USERNAME,
        )

        assert result.name == "Updated"
        assert result.description == "New desc"
        assert result.org_wide is True

    def test_raises_for_system_view(self, db_create_system_view):
        view = db_create_system_view()

        with pytest.raises(ViewPermissionError):
            update_view(str(view.id), {"name": "Hacked"}, ORG_ID, USERNAME)

    def test_raises_for_non_owner(self, db_create_view):
        view = db_create_view(org_id=ORG_ID, created_by=OTHER_USER, org_wide=True)

        with pytest.raises(ViewPermissionError):
            update_view(str(view.id), {"name": "Hacked"}, ORG_ID, USERNAME)

    def test_raises_for_nonexistent_view(self, flask_app):  # noqa: ARG002
        with pytest.raises(ViewNotFoundError):
            update_view(str(uuid.uuid4()), {"name": "X"}, ORG_ID, USERNAME)


class TestDeleteView:
    def test_deletes_own_view(self, db_create_view):
        view = db_create_view(org_id=ORG_ID, created_by=USERNAME)

        delete_view(str(view.id), ORG_ID, USERNAME)

        assert db.session.get(InventoryView, view.id) is None

    def test_raises_for_system_view(self, db_create_system_view):
        view = db_create_system_view()

        with pytest.raises(ViewPermissionError):
            delete_view(str(view.id), ORG_ID, USERNAME)

    def test_raises_for_non_owner(self, db_create_view):
        view = db_create_view(org_id=ORG_ID, created_by=OTHER_USER, org_wide=True)

        with pytest.raises(ViewPermissionError):
            delete_view(str(view.id), ORG_ID, USERNAME)

    def test_raises_for_nonexistent_view(self, flask_app):  # noqa: ARG002
        with pytest.raises(ViewNotFoundError):
            delete_view(str(uuid.uuid4()), ORG_ID, USERNAME)

    def test_raises_for_view_from_other_org(self, db_create_view):
        view = db_create_view(org_id=OTHER_ORG, created_by=OTHER_USER)

        with pytest.raises(ViewNotFoundError):
            delete_view(str(view.id), ORG_ID, USERNAME)


class TestCloneView:
    def test_clones_view(self, db_create_view):
        original = db_create_view(name="Original", org_id=ORG_ID, created_by=OTHER_USER, org_wide=True)

        result = clone_view(str(original.id), ORG_ID, USERNAME)

        assert result.name == f"{CLONE_NAME_PREFIX}Original"
        assert result.created_by == USERNAME
        assert result.org_wide is False
        assert result.configuration == VALID_CONFIG
        assert result.id != original.id

    def test_clones_system_view(self, db_create_system_view):
        system = db_create_system_view(name="System View")

        result = clone_view(str(system.id), ORG_ID, USERNAME)

        assert result.name == f"{CLONE_NAME_PREFIX}System View"
        assert result.org_id == ORG_ID
        assert result.is_system_view is False

    def test_clone_truncates_long_name(self, db_create_view):
        from app.models.views import MAX_VIEW_NAME_LENGTH

        long_name = "A" * MAX_VIEW_NAME_LENGTH
        original = db_create_view(name=long_name, org_id=ORG_ID, created_by=USERNAME)

        result = clone_view(str(original.id), ORG_ID, USERNAME)

        assert len(result.name) == MAX_VIEW_NAME_LENGTH
        assert result.name.startswith(CLONE_NAME_PREFIX)

    def test_clone_deep_copies_configuration(self, db_create_view):
        config = {"columns": [{"key": "id", "visible": True}], "filters": {"os": "RHEL"}}
        original = db_create_view(configuration=config, org_id=ORG_ID, created_by=USERNAME)

        result = clone_view(str(original.id), ORG_ID, USERNAME)

        assert result.configuration == config

    def test_raises_for_nonexistent_source(self, flask_app):  # noqa: ARG002
        with pytest.raises(ViewNotFoundError):
            clone_view(str(uuid.uuid4()), ORG_ID, USERNAME)


class TestSerializeView:
    def test_serializes_all_fields(self, db_create_view):
        view = db_create_view(name="My View", org_id=ORG_ID, created_by=USERNAME)

        result = serialize_view(view, USERNAME)

        assert result["name"] == "My View"
        assert result["org_id"] == ORG_ID
        assert result["is_system_view"] is False
        assert result["is_owner"] is True
        assert result["created_by"] == USERNAME
        assert "created_at" in result
        assert "updated_at" in result

    def test_is_owner_false_for_other_user(self, db_create_view):
        view = db_create_view(org_id=ORG_ID, created_by=OTHER_USER, org_wide=True)

        result = serialize_view(view, USERNAME)

        assert result["is_owner"] is False

    def test_system_view_serialization(self, db_create_system_view):
        view = db_create_system_view()

        result = serialize_view(view, USERNAME)

        assert result["is_system_view"] is True
        assert result["org_id"] is None
        assert result["created_by"] is None
