# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from collections.abc import Collection
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property

import attr
from iqe.base.modeling import BaseEntity
from iqe_rbac import ApplicationRBAC
from iqe_rbac_v2_api import ApiException
from iqe_rbac_v2_api import WorkspacesApi
from iqe_rbac_v2_api import WorkspacesCreateWorkspaceRequest
from iqe_rbac_v2_api import WorkspacesCreateWorkspaceResponse
from iqe_rbac_v2_api import WorkspacesPatchWorkspaceRequest
from iqe_rbac_v2_api import WorkspacesPatchWorkspaceResponse
from iqe_rbac_v2_api import WorkspacesRead200Response
from iqe_rbac_v2_api import WorkspacesUpdateWorkspaceRequest
from iqe_rbac_v2_api import WorkspacesUpdateWorkspaceResponse
from iqe_rbac_v2_api import WorkspacesWorkspace
from iqe_rbac_v2_api import WorkspacesWorkspaceListResponse
from iqe_rbac_v2_api import WorkspacesWorkspaceTypes
from iqe_rbac_v2_api import WorkspacesWorkspaceTypesQueryParam

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils import is_global_account
from iqe_host_inventory.utils.api_utils import accept_when
from iqe_host_inventory.utils.datagen_utils import generate_display_name

WORKSPACE_NOT_CREATED_ERROR = Exception("Workspace wasn't successfully created")
WORKSPACE_NOT_UPDATED_ERROR = Exception("Workspace wasn't successfully updated")
WORKSPACE_NOT_DELETED_ERROR = Exception("Workspace wasn't successfully deleted")

type WORKSPACE_OR_ID = WorkspacesWorkspace | str
type WORKSPACE_OR_WORKSPACES = WORKSPACE_OR_ID | Collection[WORKSPACE_OR_ID]


logger = logging.getLogger(__name__)


@dataclass()
class WorkspaceData:
    """Used in 'create_workspaces' method"""

    parent_id: str | None = None
    name: str | None = None
    description: str | None = None


def _id_from_workspace(workspace: WORKSPACE_OR_ID) -> str:
    return workspace if isinstance(workspace, str) else workspace.id


def _ids_from_workspaces(workspaces: WORKSPACE_OR_WORKSPACES) -> list[str]:
    if isinstance(workspaces, Collection) and not isinstance(workspaces, str):
        return [_id_from_workspace(workspace) for workspace in workspaces]
    return [_id_from_workspace(workspaces)]


def _sort_workspaces_for_deletion(
    workspace_details: dict[str, WorkspacesWorkspace],
    workspace_ids: list[str],
) -> list[str]:
    """Sort workspaces so children are deleted before parents (children first)."""

    depth_cache: dict[str, int] = {}

    def get_depth(ws_id: str, seen: set[str] | None = None) -> int:
        # Unresolved or missing details: treat as root-level
        if ws_id not in workspace_details:
            return 0

        if ws_id in depth_cache:
            return depth_cache[ws_id]

        if seen is None:
            seen = set()
        # Basic cycle guard: put cycles at depth 0
        if ws_id in seen:
            return 0
        seen.add(ws_id)

        parent_id = workspace_details[ws_id].parent_id
        if not parent_id or parent_id not in workspace_details:
            depth = 0
        else:
            depth = 1 + get_depth(parent_id, seen)

        depth_cache[ws_id] = depth
        return depth

    # Higher depth first: children before parents
    return sorted(workspace_ids, key=get_depth, reverse=True)


@attr.s
class WorkspacesAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def _rbac(self) -> ApplicationRBAC:
        return self.application.rbac

    @cached_property
    def raw_api(self) -> WorkspacesApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class, this should be used only for negative validation testing.
        """
        return self._rbac.rest_client_v2.workspaces_api

    def create_workspace(
        self,
        name: str,
        *,
        parent_id: str | None = None,
        description: str | None = None,
        wait_for_created: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> WorkspacesCreateWorkspaceResponse:
        """Create a new workspace and return the response from the
        POST /rbac/v2/workspaces endpoint

        :param str name: (required) A workspace name
        :param str parent_id: The workspace parent id
            If not set, this method will set it to the pre-defined Default Workspace id
            Default: Default Workspace id
        :param str description: The workspace description
        :param bool wait_for_created: If True, this method will wait until the workspace
            is retrievable by API (it should be available instantly)
            Default: True
        :param bool register_for_cleanup: If True, the new workspace will be registered
            for cleanup.
            Note that this doesn't mean that the workspace will actually get cleaned up.
            For that, you have to use one of the cleanup fixtures from
            `fixtures/cleanup_fixtures.py`.  By selecting the proper fixture, you can
            choose when you want the workspace to be deleted.  Look at conftest.py for
            example usage.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return WorkspacesCreateWorkspaceResponse: Created workspace
        """
        if parent_id is None:
            parent_id = self.get_default_workspace().id

        if description is None:
            description = f"Workspace {name}, parent {parent_id}"

        request = WorkspacesCreateWorkspaceRequest(
            parent_id=parent_id, name=name, description=description
        )
        created_workspace = self.raw_api.workspaces_create(request)

        if wait_for_created:
            self.wait_for_created(created_workspace)

        if register_for_cleanup:
            self._host_inventory.cleanup.add_workspaces(created_workspace, scope=cleanup_scope)

        return created_workspace

    def create_workspaces(
        self,
        data: Iterable[WorkspaceData],
        *,
        wait_for_created: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> list[WorkspacesCreateWorkspaceResponse]:
        """Create multiple workspaces and return a list of created workspaces

        :param Iterable[WorkspaceData] data: (required) A sequence of data used for
            creating workspaces.
            The workspace data is represented by a WorkspaceData object.  If a workspace
            name is not provided, a random one will be generated.
        :param bool wait_for_created: If True, this method will wait until the workspace is
            retrievable by API (it should be available instantly)
            Default: True
        :param bool register_for_cleanup: If True, the new workspaces will be
            registered for a cleanup.
            Note that this doesn't mean that the workspaces will actually get cleaned up.
            For that you have to use one of the cleanup fixtures from
            `fixtures/cleanup_fixtures.py`.  By selecting a proper fixture, you can
            choose when you want the workspace to be deleted.  Look at conftest.py for
            example usage.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return list[WorkspacesCreateWorkspaceResponse]: Created workspaces (responses
            from POST /rbac/v2/workspaces)
        """
        workspaces = []
        for workspace_data in data:
            if workspace_data.name is None:
                workspace_data.name = generate_display_name()

            workspaces.append(
                self.create_workspace(
                    name=workspace_data.name,
                    parent_id=workspace_data.parent_id,
                    description=workspace_data.description,
                    wait_for_created=False,
                    register_for_cleanup=register_for_cleanup,
                    cleanup_scope=cleanup_scope,
                )
            )

        if wait_for_created:
            self.wait_for_created(workspaces)

        return workspaces

    def wait_for_created(
        self,
        workspaces: WORKSPACE_OR_WORKSPACES,
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = WORKSPACE_NOT_CREATED_ERROR,
    ) -> list[WorkspacesWorkspace]:
        """Wait until the workspaces are successfully created and retrievable by API

        :param WORKSPACE_OR_WORKSPACES workspaces: (required) Either a single workspace
            or a list of workspaces.
            A workspace can be represented either by its ID (str) or a workspace object
        :param float delay: A delay in seconds between attempts to retrieve the workspaces
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the workspaces
            Default: 10
        :param Exception error: An error to raise when the workspaces are not retrievable.
            If `None`, then no error will be raised and the method will finish successfully.
        :return list[WorkspacesWorkspace]: Retrieved workspaces
        """
        workspace_ids = set(_ids_from_workspaces(workspaces))

        def get_workspaces() -> list[WorkspacesWorkspace]:
            return self.get_workspaces_by_id(workspaces)

        def found_all(response_workspaces: list[WorkspacesWorkspace]) -> bool:
            found_ids = {workspace.id for workspace in response_workspaces}
            if found_ids == workspace_ids:
                return True

            logger.info(f"Workspace IDs missing: {workspace_ids - found_ids}")
            return False

        return accept_when(
            get_workspaces, is_valid=found_all, delay=delay, retries=retries, error=error
        )

    def wait_for_updated(
        self,
        workspace: WORKSPACE_OR_ID,
        *,
        name: str | None = None,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = WORKSPACE_NOT_UPDATED_ERROR,
    ) -> WorkspacesWorkspace:
        """Wait until the workspace is successfully updated and retrievable by API

        :param WORKSPACE_OR_ID workspace: (required) A single workspace
            A workspace can be represented either by its ID (str) or a workspace object
        :param str name: Workspace name after the update
        :param float delay: A delay in seconds between attempts to retrieve the workspace
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the workspace
            Default: 10
        :param Exception error: An error to raise when the workspace is not retrievable.
            If `None`, then no error will be raised and the method will finish successfully.
        :return WorkspacesWorkspace: Retrieved workspace
        """

        def get_workspace() -> WorkspacesWorkspace:
            return self.get_workspace_by_id(workspace)

        def updated(response_workspace: WorkspacesWorkspace) -> bool:
            return response_workspace.name == name

        return accept_when(
            get_workspace, is_valid=updated, delay=delay, retries=retries, error=error
        )

    def get_root_workspace(self) -> WorkspacesWorkspace:
        """
        Get the root workspace.  This is a special pre-defined workspace per account.
        """
        return self.get_workspaces(
            type=WorkspacesWorkspaceTypesQueryParam.ROOT,
        )[0]

    def get_ungrouped_workspace(self) -> WorkspacesWorkspace:
        """
        Get the ungrouped workspace.  This is a special pre-defined workspace per account.
        """
        return self.get_workspaces(
            type=WorkspacesWorkspaceTypesQueryParam.UNGROUPED_MINUS_HOSTS,
        )[0]

    def get_default_workspace(self) -> WorkspacesWorkspace:
        """
        Get the default workspace.  This is a special pre-defined workspace per account.
        """
        return self.get_workspaces(
            type=WorkspacesWorkspaceTypesQueryParam.DEFAULT,
        )[0]

    def get_workspaces_response(
        self,
        *,
        type: WorkspacesWorkspaceTypesQueryParam | None = WorkspacesWorkspaceTypes.STANDARD,
        limit: int | None = 10000,
        offset: int | None = None,
    ) -> WorkspacesWorkspaceListResponse:
        """Get workspaces api response.  By default, all standard workspaces are
        returned.
        Note that the rbac api default limit is 10 and currently has no max value.  For
        convenience, this method sets an arbitrarily high limit so that a caller won't
        have to page through multiple api requests.  If desired, limit and offset can still
        be set.

        :param WorkspacesWorkspaceTypesQueryParam type: Filter by workspace type (enum).
            If not specified, all standard workspaces are returned.
            Possible values:
                WorkspacesWorkspaceTypes.ALL
                WorkspacesWorkspaceTypes.ROOT
                WorkspacesWorkspaceTypes.DEFAULT
                WorkspacesWorkspaceTypes.STANDARD
                WorkspacesWorkspaceTypes.UNGROUPED_MINUS_HOSTS
            Default: WorkspacesWorkspaceTypes.STANDARD
        :param int limit: Number of items to return
            Default: 10000
        :param int offset: An offset into the items returned
            Default: None
        :return WorkspacesWorkspaceListResponse: List of retrieved workspaces
        """
        return self.raw_api.workspaces_list(
            type=type,
            limit=limit,
            offset=offset,
        )

    def get_workspaces(
        self,
        *,
        type: WorkspacesWorkspaceTypesQueryParam | None = WorkspacesWorkspaceTypes.STANDARD,
        limit: int | None = 10000,
        offset: int | None = None,
    ) -> list[WorkspacesWorkspace]:
        """Get list of workspaces.  By default, all standard workspaces are returned
        Note that the rbac api default limit is 10 and currently has no max value.  For
        convenience, this method sets an arbitrarily high limit so that a caller won't
        have to page through multiple api requests.  If desired, limit and offset can still
        be set.

        :param WorkspacesWorkspaceTypesQueryParam type: Filter by workspace type (enum).
            Values:
                WorkspacesWorkspaceTypes.ALL
                WorkspacesWorkspaceTypes.ROOT
                WorkspacesWorkspaceTypes.DEFAULT
                WorkspacesWorkspaceTypes.STANDARD
                WorkspacesWorkspaceTypes.UNGROUPED_MINUS_HOSTS
            Default: WorkspacesWorkspaceTypes.STANDARD
        :param int limit: Number of items to return
            Default: 10000
        :param int offset: An offset into the items returned
            Default: None
        :return list[WorkspacesWorkspace]: List of retrieved workspaces
        """
        return self.get_workspaces_response(
            type=type,
            limit=limit,
            offset=offset,
        ).data

    def get_workspaces_by_id(
        self,
        workspaces: WORKSPACE_OR_WORKSPACES,
    ) -> list[WorkspacesWorkspace]:
        """Get workspaces by their IDs, return list of workspaces

        :param WORKSPACE_OR_WORKSPACES workspaces: (required) Either a single workspace
            or a list of workspaces
            A workspace can be represented either by its ID (str) or a workspace object
        :return list[WorkspacesWorkspace]: Retrieved workspaces
        """
        workspace_ids = _ids_from_workspaces(workspaces)
        return [self.get_workspace_by_id(workspace_id) for workspace_id in workspace_ids]

    def get_workspace_by_id(self, workspace: WORKSPACE_OR_ID) -> WorkspacesWorkspace:
        """Get a single workspace by its ID

        :param WORKSPACE_OR_ID workspace: (required) A single workspace
            A workspace can be represented either by its ID (str) or a workspace object
        :return WorkspacesWorkspace: Retrieved workspace
        """
        return self.get_workspace_by_id_response(workspace).actual_instance

    def get_workspace_by_id_response(
        self, workspace: WORKSPACE_OR_ID
    ) -> WorkspacesRead200Response:
        """Get a single workspace by its ID

        :param WORKSPACE_OR_ID workspace: (required) A single workspace
            A workspace can be represented either by its ID (str) or a workspace object
        :return WorkspacesRead200Response: Retrieved workspace
        """
        workspace_id = _id_from_workspace(workspace)

        response = self.raw_api.workspaces_read(workspace_id)
        assert isinstance(response, WorkspacesRead200Response)

        return response

    def delete_workspaces_raw(self, workspaces: WORKSPACE_OR_WORKSPACES) -> None:
        """Send a DELETE /rbac/v2/workspaces/<workspace_id> request without exception
            catching or fancy logic

        :param WORKSPACE_OR_WORKSPACES workspaces: (required) Either a single workspace
            or a list of workspaces
            A workspace can be represented either by its ID (str) or a workspace object
        :return None
        """
        workspace_ids = _ids_from_workspaces(workspaces)
        for workspace_id in workspace_ids:
            self.raw_api.workspaces_delete(workspace_id)

    def delete_workspaces(self, workspaces: WORKSPACE_OR_WORKSPACES) -> None:
        """Delete workspaces with exception handling.

        Workspaces are sorted by hierarchy so that children are deleted before parents.
        This prevents "Unable to delete due to workspace dependencies" errors.

        :param WORKSPACE_OR_WORKSPACES workspaces: (required) Either a single workspace
            or a list of workspaces
            A workspace can be represented either by its ID (str) or a workspace object
        :return None
        """
        workspace_ids = _ids_from_workspaces(workspaces)
        if not workspace_ids:
            return

        workspace_details: dict[str, WorkspacesWorkspace] = {}
        for workspace_id in workspace_ids:
            try:
                workspace = self.get_workspace_by_id(workspace_id)
                workspace_details[workspace_id] = workspace
            except ApiException as err:
                if err.status in (403, 404):
                    logger.info(f"Workspace {workspace_id} not found, skipping fetch")
                else:
                    raise err

        sorted_ids = _sort_workspaces_for_deletion(workspace_details, workspace_ids)

        try:
            self.delete_workspaces_raw(sorted_ids)
        except ApiException as err:
            if err.status in (403, 404):
                logger.info(
                    f"Couldn't delete workspaces {sorted_ids} because they were not found."
                )
            else:
                raise err

    def delete_all_workspaces(self) -> None:
        """Delete all workspaces in the account

        WARNING: Use this method only in ephemeral or local envs, or with a separate
        account.  It will delete all standard workspaces on the account, which can affect
        tests from other plugins.

        :return None
        """
        if is_global_account(self.application):
            raise Exception("It's not safe to delete all workspaces on a global account")

        workspaces = self.get_workspaces()
        self.delete_workspaces(workspaces)

    def patch_workspace(
        self,
        workspace: WORKSPACE_OR_ID,
        *,
        name: str | None = None,
        description: str | None = None,
        wait_for_updated: bool = True,
    ) -> WorkspacesPatchWorkspaceResponse:
        """Patch a workspace and return a response from the PATCH
            /rbac/v2/workspaces/<workspace_id> endpoint

        :param WORKSPACE_OR_ID workspace: (required) A single workspace to be updated
            A workspace can be represented either by its ID (str) or a workspace object
        :param str name: A new workspace name
        :param str description: A new workspace description
        :param bool wait_for_updated: If True, wait until the workspace is updated
        :return WorkspacesPatchWorkspaceResponse: Patched workspace (response from PATCH
        /rbac/v2/workspaces/<workspace_id>)
        """
        workspace_id = _id_from_workspace(workspace)

        request = WorkspacesPatchWorkspaceRequest(name=name, description=description)
        patched_workspace = self.raw_api.workspaces_patch(workspace_id, request)

        if wait_for_updated:
            self.wait_for_updated(workspace, name=name)

        return patched_workspace

    def update_workspace(
        self,
        workspace: WORKSPACE_OR_ID,
        *,
        name: str | None = None,
        description: str | None = None,
        parent_id: str | None = None,
    ) -> WorkspacesUpdateWorkspaceResponse:
        """Update a workspace and return a response from the PUT
            /rbac/v2/workspaces/<workspace_id> endpoint

            Note: This api requires all params to be set.  For convenience, if any of
            them aren't, use the existing value.

        :param WORKSPACE_OR_ID workspace: (required) A single workspace to be updated
            A workspace can be represented either by its ID (str) or a workspace object
        :param str name: A new workspace name (has to be unique for each workspace)
        :param str description: A new workspace description
        :param str parent_id: A new workspace parent id
        :return WorkspacesUpdateWorkspaceResponse: Update workspace (response from PUT
            /rbac/v2/workspaces/<workspace_id>)
        """
        workspace_obj = (
            workspace
            if isinstance(workspace, WorkspacesWorkspace)
            else self.get_workspace_by_id(workspace)
        )

        if name is None:
            name = workspace_obj.name

        if description is None:
            description = workspace_obj.description

        if parent_id is None:
            parent_id = workspace_obj.parent_id

        workspace_id = _id_from_workspace(workspace_obj)

        request = WorkspacesUpdateWorkspaceRequest(
            name=name, description=description, parent_id=parent_id
        )
        updated_workspace = self.raw_api.workspaces_update(workspace_id, request)

        return updated_workspace
