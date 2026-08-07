# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any

import attr
from iqe.base.modeling import BaseEntity

from iqe_host_inventory.utils.api_utils import check_org_id
from iqe_host_inventory_api import ViewOut
from iqe_host_inventory_api import ViewsApi
from iqe_host_inventory_api import ViewsListOut

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

VIEW_OR_ID = ViewOut | str

logger = logging.getLogger(__name__)


def _id_from_view(view: VIEW_OR_ID) -> str:
    return view if isinstance(view, str) else view.id


@attr.s
class ViewsAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def raw_api(self) -> ViewsApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class this should be used only for negative validation testing.
        """
        return self._host_inventory.rest_client.views_api

    @check_org_id
    def get_views_response(
        self,
        *,
        per_page: int | None = None,
        page: int | None = None,
        **api_kwargs: Any,
    ) -> ViewsListOut:
        """Get list of views, return OpenAPI client response.

        :param int per_page: Number of items to return per page (default: 50)
        :param int page: Page number (default: 1)
        :return ViewsListOut: API response
        """
        with self._host_inventory.apis.measure_time("GET /views"):
            return self.raw_api.api_views_get_views_list(
                per_page=per_page,
                page=page,
                **api_kwargs,
            )

    def get_views(
        self,
        *,
        per_page: int | None = None,
        page: int | None = None,
        **api_kwargs: Any,
    ) -> list[ViewOut]:
        """Get list of views, return list of view objects.

        :param int per_page: Number of items to return per page (default: 50)
        :param int page: Page number (default: 1)
        :return list[ViewOut]: List of views
        """
        return self.get_views_response(
            per_page=per_page,
            page=page,
            **api_kwargs,
        ).results

    @check_org_id
    def get_view_by_id(self, view: VIEW_OR_ID, **api_kwargs: Any) -> ViewOut:
        """Get a single view by its ID.

        :param VIEW_OR_ID view: A view ID string or ViewOut object
        :return ViewOut: Retrieved view
        """
        view_id = _id_from_view(view)
        with self._host_inventory.apis.measure_time("GET /views/<view_id>"):
            return self.raw_api.api_views_get_view_by_id(view_id, **api_kwargs)

    @check_org_id
    def create_view(
        self,
        name: str,
        *,
        configuration: dict[str, Any] | None = None,
        description: str | None = None,
        org_wide: bool | None = None,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
        **api_kwargs: Any,
    ) -> ViewOut:
        """Create a new inventory view.

        :param str name: View name (required)
        :param dict configuration: View configuration (columns, sort, filters)
        :param str description: View description
        :param bool org_wide: Whether the view is visible to the whole org
        :param bool register_for_cleanup: Register the view for automatic cleanup
        :param str cleanup_scope: Scope for cleanup (function, class, module, package, session)
        :return ViewOut: Created view
        """
        data: dict[str, Any] = {"name": name}
        if configuration is not None:
            data["configuration"] = configuration
        if description is not None:
            data["description"] = description
        if org_wide is not None:
            data["org_wide"] = org_wide

        with self._host_inventory.apis.measure_time("POST /views"):
            created_view: ViewOut = self.raw_api.api_views_create_view(data, **api_kwargs)

        if register_for_cleanup:
            self._host_inventory.cleanup.add_views(created_view.id, scope=cleanup_scope)

        return created_view

    @check_org_id
    def update_view(
        self,
        view: VIEW_OR_ID,
        *,
        name: str | None = None,
        description: str | None = None,
        configuration: dict[str, Any] | None = None,
        org_wide: bool | None = None,
        **api_kwargs: Any,
    ) -> ViewOut:
        """Update an existing inventory view (partial update).

        :param VIEW_OR_ID view: A view ID string or ViewOut object
        :param str name: Updated view name
        :param str description: Updated description
        :param dict configuration: Updated configuration
        :param bool org_wide: Updated org_wide flag
        :return ViewOut: Updated view
        """
        view_id = _id_from_view(view)
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
            return self.raw_api.api_views_update_view(view_id, data, **api_kwargs)

    @check_org_id
    def delete_view(self, view: VIEW_OR_ID, **api_kwargs: Any) -> None:
        """Delete an inventory view.

        :param VIEW_OR_ID view: A view ID string or ViewOut object
        """
        view_id = _id_from_view(view)
        with self._host_inventory.apis.measure_time("DELETE /views/<view_id>"):
            self.raw_api.api_views_delete_view(view_id, **api_kwargs)

    def delete_views(self, view_ids: set[str] | list[str]) -> None:
        """Delete multiple views, suppressing 404 and 403 errors.

        404 is expected when a view was already deleted (e.g. by the test itself).
        403 is expected for system views that cannot be deleted.

        :param view_ids: Collection of view IDs to delete
        """
        from iqe_host_inventory_api import ApiException

        for view_id in view_ids:
            try:
                self.delete_view(view_id)
            except ApiException as err:
                if err.status in (403, 404):
                    logger.info(f"Skipping cleanup for view {view_id}: HTTP {err.status}")
                else:
                    raise

    @check_org_id
    def clone_view(
        self,
        view: VIEW_OR_ID,
        *,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
        **api_kwargs: Any,
    ) -> ViewOut:
        """Clone an existing inventory view.

        :param VIEW_OR_ID view: A view ID string or ViewOut object
        :param bool register_for_cleanup: Register the cloned view for automatic cleanup
        :param str cleanup_scope: Scope for cleanup
        :return ViewOut: Cloned view
        """
        view_id = _id_from_view(view)
        with self._host_inventory.apis.measure_time("POST /views/<view_id>/clone"):
            cloned_view: ViewOut = self.raw_api.api_views_clone_view(view_id, **api_kwargs)

        if register_for_cleanup:
            self._host_inventory.cleanup.add_views(cloned_view.id, scope=cleanup_scope)

        return cloned_view
