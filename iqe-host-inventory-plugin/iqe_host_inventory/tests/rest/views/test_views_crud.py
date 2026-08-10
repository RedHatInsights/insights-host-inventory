"""Happy-path IQE tests for the Inventory Views CRUD API (/beta/views).

Covers: list, get-by-id, create, update (patch), delete, and clone.
"""

from __future__ import annotations

import logging
from uuid import UUID

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)

VALID_CONFIGURATION = {
    "columns": [
        {"key": "display_name"},
        {"key": "updated"},
    ],
    "sort": {"key": "display_name", "direction": "asc"},
}


class TestViewsList:
    """GET /beta/views"""

    def test_list_views_returns_paginated_response(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-get
            assignee: adubey
            importance: high
            title: List views returns paginated response
        """
        response = host_inventory.apis.views.get_views_response()
        assert response.total >= 0
        assert response.page == 1
        assert response.per_page == 50

    def test_created_view_appears_in_list(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-get
            assignee: adubey
            importance: high
            title: Newly created view appears in list
        """
        name = generate_display_name()
        created = host_inventory.apis.views.create_view(name, configuration=VALID_CONFIGURATION)

        views = host_inventory.apis.views.get_views()
        view_ids = {v.id for v in views}
        assert created.id in view_ids


class TestViewGetById:
    """GET /beta/views/{id}"""

    def test_get_view_by_id(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-get
            assignee: adubey
            importance: high
            title: Retrieve a view by its UUID
        """
        name = generate_display_name()
        created = host_inventory.apis.views.create_view(name, configuration=VALID_CONFIGURATION)

        fetched = host_inventory.apis.views.get_view_by_id(created)
        assert fetched.id == created.id
        assert fetched.name == name

    def test_get_nonexistent_view_returns_404(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-get
            assignee: adubey
            importance: medium
            title: GET for nonexistent view returns 404
        """
        fake_id = generate_uuid()
        with raises_apierror(404):
            host_inventory.apis.views.get_view_by_id(fake_id)


class TestViewCreate:
    """POST /beta/views"""

    def test_create_view_with_configuration(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-post
            assignee: adubey
            importance: critical
            title: Create a view with columns and sort configuration
        """
        name = generate_display_name()
        description = "IQE test view"
        view = host_inventory.apis.views.create_view(
            name,
            configuration=VALID_CONFIGURATION,
            description=description,
        )

        assert UUID(view.id)
        assert view.name == name
        assert view.description == description
        assert view.is_owner is True
        assert view.is_system_view is False
        assert view.org_wide is False

    def test_create_view_validation_rejects_invalid_column(
        self, host_inventory: ApplicationHostInventory
    ):
        """
        metadata:
            requirements: inv-views-post
            assignee: adubey
            importance: high
            title: Create view with invalid column key returns 400
        """
        name = generate_display_name()
        bad_config = {"columns": [{"key": "totally_fake_field"}]}
        with raises_apierror(400, "Invalid column key"):
            host_inventory.apis.views.raw_api.api_views_create_view({
                "name": name,
                "configuration": bad_config,
            })


class TestViewUpdate:
    """PATCH /beta/views/{id}"""

    def test_update_view_name(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-patch
            assignee: adubey
            importance: critical
            title: PATCH updates the view name while preserving other fields
        """
        original_name = generate_display_name()
        view = host_inventory.apis.views.create_view(
            original_name, configuration=VALID_CONFIGURATION
        )

        new_name = generate_display_name()
        updated = host_inventory.apis.views.update_view(view, name=new_name)

        assert updated.id == view.id
        assert updated.name == new_name
        assert updated.created_by == view.created_by

    def test_update_view_configuration(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-patch
            assignee: adubey
            importance: high
            title: PATCH updates view configuration
        """
        name = generate_display_name()
        view = host_inventory.apis.views.create_view(name, configuration=VALID_CONFIGURATION)

        new_config = {
            "columns": [{"key": "display_name"}, {"key": "updated"}, {"key": "last_check_in"}],
            "sort": {"key": "updated", "direction": "desc"},
        }
        updated = host_inventory.apis.views.update_view(view, configuration=new_config)

        assert updated.id == view.id
        assert len(updated.configuration.columns) == 3

    def test_update_nonexistent_view_returns_404(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-patch
            assignee: adubey
            importance: medium
            title: PATCH returns 404 when updating a nonexistent view
        """
        fake_id = generate_uuid()
        with raises_apierror(404):
            host_inventory.apis.views.raw_api.api_views_patch_view(
                fake_id, {"name": generate_display_name()}
            )


class TestViewDelete:
    """DELETE /beta/views/{id}"""

    def test_delete_view(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-delete
            assignee: adubey
            importance: critical
            title: Delete a view and confirm it is gone
        """
        name = generate_display_name()
        view = host_inventory.apis.views.create_view(
            name, configuration=VALID_CONFIGURATION, register_for_cleanup=False
        )

        response = host_inventory.apis.views.raw_api.api_views_delete_view_with_http_info(view.id)
        assert response[1] == 204

        with raises_apierror(404):
            host_inventory.apis.views.get_view_by_id(view.id)

    def test_delete_nonexistent_view_returns_404(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-delete
            assignee: adubey
            importance: medium
            title: Delete a nonexistent view returns 404
        """
        fake_id = generate_uuid()
        with raises_apierror(404):
            host_inventory.apis.views.raw_api.api_views_delete_view(fake_id)


class TestViewClone:
    """POST /beta/views/{id}/clone"""

    def test_clone_own_view(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-clone
            assignee: adubey
            importance: critical
            title: Clone own view creates a new view with 'Copy of' prefix
        """
        name = generate_display_name()
        original = host_inventory.apis.views.create_view(
            name, configuration=VALID_CONFIGURATION, description="original"
        )

        cloned = host_inventory.apis.views.clone_view(original)

        assert UUID(cloned.id)
        assert cloned.id != original.id
        assert cloned.name == f"Copy of {name}"
        assert cloned.is_owner is True
        assert cloned.org_wide is False

    def test_clone_preserves_configuration(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-clone
            assignee: adubey
            importance: high
            title: Cloned view has the same configuration as the source
        """
        name = generate_display_name()
        config = {
            "columns": [{"key": "display_name"}, {"key": "updated"}],
            "sort": {"key": "display_name", "direction": "asc"},
        }
        original = host_inventory.apis.views.create_view(name, configuration=config)
        cloned = host_inventory.apis.views.clone_view(original)

        assert len(cloned.configuration.columns) == len(original.configuration.columns)
        cloned_keys = [c.key for c in cloned.configuration.columns]
        original_keys = [c.key for c in original.configuration.columns]
        assert cloned_keys == original_keys

    def test_clone_nonexistent_view_returns_404(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-clone
            assignee: adubey
            importance: medium
            title: Clone nonexistent view returns 404
        """
        fake_id = generate_uuid()
        with raises_apierror(404):
            host_inventory.apis.views.clone_view(fake_id)

    def test_clone_and_modify_independently(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-clone
            assignee: adubey
            importance: high
            title: Modifying a clone does not affect the original view
        """
        name = generate_display_name()
        original = host_inventory.apis.views.create_view(name, configuration=VALID_CONFIGURATION)

        cloned = host_inventory.apis.views.clone_view(original)
        new_name = generate_display_name()
        host_inventory.apis.views.update_view(cloned, name=new_name)

        refetched_original = host_inventory.apis.views.get_view_by_id(original)
        assert refetched_original.name == name


class TestViewCrossOrg:
    """Cross-org isolation for views"""

    @pytest.mark.ephemeral
    def test_view_not_visible_to_other_org(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_secondary: ApplicationHostInventory,
    ):
        """
        metadata:
            requirements: inv-views-get
            assignee: adubey
            importance: critical
            title: View created by one org is not visible to another org
        """
        name = generate_display_name()
        view = host_inventory.apis.views.create_view(name, configuration=VALID_CONFIGURATION)

        secondary_views = host_inventory_secondary.apis.views.get_views()
        secondary_view_ids = {v.id for v in secondary_views}
        assert view.id not in secondary_view_ids
