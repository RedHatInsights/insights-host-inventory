"""IQE e2e coverage for default view preference (/beta/views + /beta/views/default).

Keeps scenarios lean: unit/API tests already cover validation, 404/403, upsert,
idempotent delete, visibility fallback, and cache behavior. These tests only
verify the cross-endpoint flow against a real environment.
"""

from __future__ import annotations

import logging
from uuid import UUID

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_display_name

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)

VALID_CONFIGURATION = {
    "columns": [
        {"key": "display_name"},
        {"key": "updated"},
    ],
}


class TestDefaultViewE2E:
    """Cross-endpoint default view flow (list ↔ pin ↔ unpin)."""

    def test_list_includes_default_view_id(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-default
            assignee: adubey
            importance: high
            title: GET /views includes a default_view_id in a real environment
        """
        body = host_inventory.apis.views.get_views_json()
        assert "default_view_id" in body
        assert UUID(body["default_view_id"])

    def test_pin_and_unpin_roundtrip(self, host_inventory: ApplicationHostInventory):
        """
        metadata:
            requirements: inv-views-default
            assignee: adubey
            importance: critical
            title: Pin then unpin updates default_view_id on subsequent list calls
        """
        views_api = host_inventory.apis.views

        # Clear any leftover preference so baseline is the system default.
        views_api.delete_default_view()
        baseline = views_api.get_views_json()["default_view_id"]

        view = views_api.create_view(generate_display_name(), configuration=VALID_CONFIGURATION)
        pinned = views_api.set_default_view(view["id"])
        assert pinned["id"] == view["id"]
        assert views_api.get_views_json()["default_view_id"] == view["id"]

        response = views_api.delete_default_view()
        assert response.status_code == 204
        assert views_api.get_views_json()["default_view_id"] == baseline
