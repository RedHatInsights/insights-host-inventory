# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from collections.abc import Iterable
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any

import attr
import requests
from iqe.base.modeling import BaseEntity

from iqe_host_inventory.modeling.base_api_wrapper import BaseAPIWrapper
from iqe_host_inventory.utils.api_utils import build_query_string

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)


@attr.s
class ViewsAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def _base_wrapper(self) -> BaseAPIWrapper:
        return BaseAPIWrapper(self.application)

    def get_views_response(
        self,
        *,
        per_page: int | None = None,
        page: int | None = None,
    ) -> requests.Response:
        """Get list of views, return raw HTTP response.

        :param int per_page: Number of items to return per page (default: 50)
        :param int page: Page number (default: 1)
        :return requests.Response: API response
        """
        query = build_query_string(per_page=per_page, page=page)
        path = "/beta/views"
        if query:
            path += "?" + query

        with self._host_inventory.apis.measure_time("GET /views"):
            response = self._base_wrapper.get(path)
        response.raise_for_status()
        return response

    def get_views_json(
        self,
        *,
        per_page: int | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        """Get list of views, return parsed JSON body.

        :param int per_page: Number of items to return per page (default: 50)
        :param int page: Page number (default: 1)
        :return dict: Dictionary with total, count, page, per_page, results
        """
        return self.get_views_response(per_page=per_page, page=page).json()

    def get_views(
        self,
        *,
        per_page: int | None = None,
        page: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get list of views, return just the results list.

        :param int per_page: Number of items to return per page (default: 50)
        :param int page: Page number (default: 1)
        :return list[dict]: List of view dicts
        """
        return self.get_views_json(per_page=per_page, page=page)["results"]

    def get_view_by_id(self, view_id: str) -> dict[str, Any]:
        """Get a single view by its ID.

        :param str view_id: View UUID
        :return dict: View data
        """
        with self._host_inventory.apis.measure_time("GET /views/<view_id>"):
            response = self._base_wrapper.get(f"/beta/views/{view_id}")
        response.raise_for_status()
        return response.json()

    def create_view(
        self,
        name: str,
        *,
        configuration: dict[str, Any] | None = None,
        description: str | None = None,
        org_wide: bool | None = None,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> dict[str, Any]:
        """Create a new inventory view.

        :param str name: View name (required)
        :param dict configuration: View configuration (columns, sort, filters, host_filters)
        :param str description: View description
        :param bool org_wide: Whether the view is visible to the whole org
        :param bool register_for_cleanup: Register the view for automatic cleanup
        :param str cleanup_scope: Scope for cleanup (function, class, module, package, session)
        :return dict: Created view data
        """
        data: dict[str, Any] = {"name": name}
        if configuration is not None:
            data["configuration"] = configuration
        if description is not None:
            data["description"] = description
        if org_wide is not None:
            data["org_wide"] = org_wide

        with self._host_inventory.apis.measure_time("POST /views"):
            response = self._base_wrapper.post("/beta/views", json=data)
        response.raise_for_status()
        created_view = response.json()

        if register_for_cleanup:
            self._host_inventory.cleanup.add_views(created_view["id"], scope=cleanup_scope)

        return created_view

    def update_view(
        self,
        view_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        configuration: dict[str, Any] | None = None,
        org_wide: bool | None = None,
    ) -> dict[str, Any]:
        """Update an existing inventory view (partial update).

        :param str view_id: View UUID
        :param str name: Updated view name
        :param str description: Updated description
        :param dict configuration: Updated configuration
        :param bool org_wide: Updated org_wide flag
        :return dict: Updated view data
        """
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if configuration is not None:
            data["configuration"] = configuration
        if org_wide is not None:
            data["org_wide"] = org_wide

        with self._host_inventory.apis.measure_time("PATCH /views/<view_id>"):
            response = self._base_wrapper.patch(f"/beta/views/{view_id}", json=data)
        response.raise_for_status()
        return response.json()

    def delete_view(self, view_id: str) -> requests.Response:
        """Delete an inventory view.

        :param str view_id: View UUID
        :return requests.Response: Raw HTTP response
        """
        with self._host_inventory.apis.measure_time("DELETE /views/<view_id>"):
            response = self._base_wrapper.delete(f"/beta/views/{view_id}")
        response.raise_for_status()
        return response

    def delete_views(self, view_ids: Iterable[str]) -> None:
        """Delete multiple views, suppressing 404 errors.

        404 is expected when a view was already deleted (e.g. by the test itself).

        :param view_ids: Collection of view IDs to delete (must not be a bare str)
        """
        if isinstance(view_ids, str):
            view_ids = [view_ids]

        for view_id in view_ids:
            try:
                self.delete_view(view_id)
            except requests.HTTPError as err:
                if err.response is not None and err.response.status_code == 404:
                    logger.info(f"Skipping cleanup for view {view_id}: HTTP 404")
                else:
                    raise

    def clone_view(
        self,
        view_id: str,
        *,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> dict[str, Any]:
        """Clone an existing inventory view.

        :param str view_id: View UUID
        :param bool register_for_cleanup: Register the cloned view for automatic cleanup
        :param str cleanup_scope: Scope for cleanup
        :return dict: Cloned view data
        """
        with self._host_inventory.apis.measure_time("POST /views/<view_id>/clone"):
            response = self._base_wrapper.post(f"/beta/views/{view_id}/clone")
        response.raise_for_status()
        cloned_view = response.json()

        if register_for_cleanup:
            self._host_inventory.cleanup.add_views(cloned_view["id"], scope=cleanup_scope)

        return cloned_view
