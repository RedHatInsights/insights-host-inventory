from __future__ import annotations

import inspect
from functools import partial
from functools import wraps
from http import HTTPStatus
from typing import Any
from uuid import UUID

from app_common_python import LoadedConfig
from flask import abort
from flask import current_app
from flask import g
from flask import request
from requests import Session
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
from urllib3.util.retry import Retry

from api.metrics import outbound_http_response_time
from app import IDENTITY_HEADER
from app import REQUEST_ID_HEADER
from app.auth import get_current_identity
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.auth.rbac import KesselPermission
from app.auth.rbac import KesselResourceType
from app.auth.rbac import KesselResourceTypes
from app.auth.rbac import RbacPermission
from app.auth.rbac import RbacResourceType
from app.common import inventory_config
from app.exceptions import IdsNotFoundError
from app.exceptions import ResourceNotFoundException
from app.instrumentation import rbac_failure
from app.instrumentation import rbac_group_permission_denied
from app.instrumentation import rbac_permission_denied
from app.logging import get_logger
from app.logging import threadctx
from lib.feature_flags import FLAG_INVENTORY_API_READ_ONLY
from lib.feature_flags import FLAG_INVENTORY_KESSEL_PHASE_1
from lib.feature_flags import get_flag_value
from lib.kessel import Kessel
from lib.kessel import get_kessel_client

logger = get_logger(__name__)

RBAC_ROUTE = "/api/rbac/v1/access/?application="
RBAC_V2_ROUTE = "/api/rbac/v2/"
RBAC_PRIVATE_UNGROUPED_ROUTE = "/_private/_s2s/workspaces/ungrouped/"
CHECKED_TYPES = [IdentityType.USER, IdentityType.SERVICE_ACCOUNT]
RETRY_STATUSES = [500, 502, 503, 504]


def get_rbac_url(app: str) -> str:
    return inventory_config().rbac_endpoint + RBAC_ROUTE + app


def get_rbac_v2_url(endpoint: str) -> str:
    return inventory_config().rbac_endpoint + RBAC_V2_ROUTE + endpoint


def _get_rbac_workspace_url(workspace_id: str | None = None, query_params: dict | None = None) -> str:
    """
    Build RBAC v2 workspace URL with optional workspace ID and query parameters.

    Args:
        workspace_id: Optional workspace ID for specific workspace operations
        query_params: Optional query parameters (e.g., {"type": "default", "limit": 1})

    Returns:
        Complete RBAC v2 workspace URL
    """
    endpoint = f"workspaces/{workspace_id}/" if workspace_id else "workspaces/"
    if query_params:
        param_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
        endpoint += f"?{param_string}"

    return get_rbac_v2_url(endpoint)


def get_rbac_private_url() -> str:
    return inventory_config().rbac_endpoint + RBAC_PRIVATE_UNGROUPED_ROUTE


def _build_rbac_request_headers(identity_header: str | None = None, request_id_header: str | None = None) -> dict:
    request_headers = {
        IDENTITY_HEADER: identity_header or request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request_id_header or request.headers.get(REQUEST_ID_HEADER),
    }
    return request_headers


def _execute_rbac_http_request(  # type: ignore[return]
    method: str,
    rbac_endpoint: str,
    request_headers: dict,
    request_data: dict | None = None,
    request_params: dict | None = None,
    skip_not_found: bool = False,
) -> dict | None:
    """
    Generic RBAC request handler that consolidates common functionality.

    NOTE: This function does NOT check bypass flags (bypass_rbac or bypass_kessel).
    Callers are responsible for checking the appropriate bypass flag before calling
    this function to maintain clear separation of concerns.

    Args:
        method: HTTP method ('GET', 'POST', 'DELETE', or 'PATCH')
        rbac_endpoint: The RBAC endpoint URL
        request_headers: Headers for the request
        request_data: JSON data for POST/PATCH requests
        request_params: Query parameters for GET requests
        skip_not_found: If True, 404 errors raise ResourceNotFoundException instead of aborting

    Returns:
        Parsed JSON response data from the RBAC endpoint
    """
    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(rbac_endpoint, HTTPAdapter(max_retries=retry_config))
    timeout = inventory_config().rbac_timeout

    try:
        with outbound_http_response_time.labels("rbac").time():
            # Build common parameters shared by all HTTP methods
            common_kwargs = {
                "url": rbac_endpoint,
                "headers": request_headers,
                "timeout": timeout,
                "verify": LoadedConfig.tlsCAPath,
            }

            # Add method-specific parameters
            method_upper = method.upper()
            if method_upper == "GET":
                common_kwargs["params"] = request_params
            elif method_upper in {"POST", "PATCH"}:
                common_kwargs["json"] = request_data
            elif method_upper != "DELETE":
                raise ValueError(f"Unsupported method: {method}")

            # Dynamically call the appropriate HTTP method
            http_method = getattr(request_session, method_upper.lower())
            rbac_response = http_method(**common_kwargs)

            rbac_response.raise_for_status()
            return rbac_response.json() if rbac_response.text else None
    except HTTPError as e:
        status_code = e.response.status_code
        if status_code == 404 and skip_not_found:
            # For 404 errors with skip_not_found=True, raise ResourceNotFoundException
            # instead of aborting. This allows the calling code to handle missing
            # resources gracefully (e.g., when deleting a workspace that may not exist)
            try:
                detail = e.response.json().get("detail", e.response.text)
            except Exception:
                detail = e.response.text  # fallback if JSON can't be parsed
            logger.info(f"RBAC 404 not found (skip_not_found=True): {detail}")
            raise ResourceNotFoundException(detail) from e
        elif 400 <= status_code < 500:
            try:
                detail = e.response.json().get("detail", e.response.text)
            except Exception:
                detail = e.response.text  # fallback if JSON can't be parsed
            logger.warning(f"RBAC client error: {status_code} - {detail}")
            abort(status_code, f"RBAC client error: {detail}")
        else:
            logger.error(f"RBAC server error: {status_code} - {e.response.text}")
            abort(503, "RBAC server error, request cannot be fulfilled")
    except Exception as e:
        rbac_failure(logger, e)
        abort(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")
    finally:
        request_session.close()


def rbac_get_request_using_endpoint_and_headers(
    rbac_endpoint: str, request_headers: dict, request_params: dict | None = None
):
    """
    Execute a GET request to an RBAC endpoint.

    NOTE: This function does NOT check bypass flags (bypass_rbac or bypass_kessel).
    Callers are responsible for checking the appropriate bypass flag before calling
    this function to maintain clear separation of concerns.
    """
    return _execute_rbac_http_request(
        method="GET",
        rbac_endpoint=rbac_endpoint,
        request_headers=request_headers,
        request_params=request_params,
    )


def get_rbac_permissions(app: str, request_header: dict):
    if inventory_config().bypass_rbac:
        return None

    resp_data = rbac_get_request_using_endpoint_and_headers(get_rbac_url(app), request_header)
    logger.debug("Fetched RBAC Data", extra={"resp_data": resp_data})
    return resp_data["data"]


# Determine whether the request should be allowed, strictly according to the given permissions.
# If any of these match, the endpoint should at least be allowed (but may have filtered results).
def _is_request_allowed_by_permission(
    rbac_permission: str, permission_base: str, resource_type: RbacResourceType, required_permission: RbacPermission
) -> bool:
    return (
        rbac_permission  # inventory:*:*
        == f"{permission_base}:{RbacResourceType.ALL.value}:{RbacPermission.ADMIN.value}"
        or rbac_permission  # inventory:{type}:*
        == f"{permission_base}:{resource_type.value}:{RbacPermission.ADMIN.value}"
        or rbac_permission  # inventory:*:(read | write)
        == f"{permission_base}:{RbacResourceType.ALL.value}:{required_permission.value}"
        or rbac_permission  # inventory:{type}:(read | write)
        == f"{permission_base}:{resource_type.value}:{required_permission.value}"
    )


# Validate RBAC response, and fetch
def _get_group_list_from_resource_definition(resource_definition: dict) -> list[str]:
    allowed_ops = ("in", "equal")

    if "attributeFilter" in resource_definition:
        operation = resource_definition["attributeFilter"].get("operation")
        if resource_definition["attributeFilter"].get("key") != "group.id":
            abort(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Invalid value for attributeFilter.key in RBAC response.",
            )
        elif operation not in allowed_ops:
            abort(
                HTTPStatus.SERVICE_UNAVAILABLE,
                (
                    "Invalid value for attributeFilter.operation in RBAC response: "
                    f"'{operation}'. Allowed values are {allowed_ops}."
                ),
            )
        elif operation == "in" and not isinstance(resource_definition["attributeFilter"]["value"], list):
            abort(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Did not receive a list for attributeFilter.value in RBAC response.",
            )
        else:
            # Validate that all values in the filter are UUIDs.
            group_list = resource_definition["attributeFilter"]["value"]
            if operation == "equal":
                group_list = [group_list]

            try:
                for gid in group_list:
                    if gid is not None:
                        UUID(gid)
            except (ValueError, TypeError):
                abort(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "Received invalid UUIDs for attributeFilter.value in RBAC response.",
                )

            return group_list
    return []


def get_rbac_filter(
    resource_type: RbacResourceType,
    required_permission: RbacPermission,
    identity: Identity,
    rbac_request_headers: dict,
    permission_base: str = "inventory",
) -> tuple[bool, dict | None]:
    # Returns a 2-item tuple:
    # 1. Whether or not the request should be allowed at all
    # 2. The filter that should be applied to the data (if allowed)
    if inventory_config().bypass_rbac:
        return True, None

    if identity.identity_type not in CHECKED_TYPES:
        if resource_type == RbacResourceType.HOSTS:
            return True, None
        else:
            return False, None

    # track that RBAC is being used to control access
    g.access_control_rule = "RBAC"
    logger.debug("access_control_rule set")

    rbac_data = get_rbac_permissions(permission_base, rbac_request_headers)
    allowed = False  # Determines whether the endpoint can be accessed at all
    allowed_group_ids = set()  # If populated, limits the allowed resources to specific group IDs

    for rbac_permission in rbac_data:
        if _is_request_allowed_by_permission(
            rbac_permission["permission"], permission_base, resource_type, required_permission
        ):
            allowed = True

            # Get the list of allowed Group IDs from the attribute filter.
            groups_attribute_filter = set()
            for resourceDefinition in rbac_permission["resourceDefinitions"]:
                group_list = _get_group_list_from_resource_definition(resourceDefinition)
                groups_attribute_filter.update(group_list)

            if groups_attribute_filter:
                # If the RBAC permission is applicable and is limited to specific group IDs,
                # add that list of group IDs to the list of allowed group IDs.
                allowed_group_ids.update(groups_attribute_filter)
            else:
                # If any applicable RBAC permission exists and is NOT limited to specific group IDs,
                # call the usual endpoint without resource-specific access limitations.
                return True, None

    # If all applicable permissions are restricted to specific groups,
    # call the endpoint with the RBAC filtering data.
    if allowed:
        return True, {"groups": allowed_group_ids}

    rbac_permission_denied(logger, required_permission.value, rbac_data)
    return False, None


def kessel_type(type) -> str:
    if type == RbacResourceType.HOSTS:
        return "host"
    elif type == RbacResourceType.STALENESS:
        return "staleness"
    elif type == RbacResourceType.ALL:
        return "all"
    else:
        return type


def kessel_verb(perm) -> str:
    if perm == RbacPermission.READ:
        return "view"
    elif perm == RbacPermission.WRITE:
        return "update"
    elif perm == RbacPermission.ADMIN:
        return "all"
    else:
        return perm


def get_kessel_filter(
    kessel_client: Kessel, current_identity: Identity, permission: KesselPermission, ids: list[str]
) -> tuple[bool, dict[str, Any] | None]:
    """
    Check Kessel permissions and return filter information.

    Returns:
        tuple[bool, dict | None]: (allowed, filter_data)
        - filter_data may contain "groups" for workspace filtering
        - filter_data may contain "unauthorized_ids" when permission is denied for specific IDs
    """
    logger.debug(
        "get_kessel_filter called",
        extra={
            "identity_type": current_identity.identity_type,
            "org_id": current_identity.org_id,
            "permission_resource_type": permission.resource_type.name if permission.resource_type else None,
            "permission_resource_permission": permission.resource_permission,
            "permission_workspace_permission": permission.workspace_permission,
            "permission_write_operation": permission.write_operation,
            "ids_count": len(ids),
            "ids": ids[:10] if ids else [],  # Log first 10 IDs for debugging
        },
    )

    if current_identity.identity_type not in CHECKED_TYPES:
        logger.debug(
            "get_kessel_filter: identity_type not in CHECKED_TYPES, bypassing check",
            extra={
                "identity_type": current_identity.identity_type,
                "checked_types": [t.value for t in CHECKED_TYPES],
                "is_host_resource": permission.resource_type == KesselResourceTypes.HOST,
            },
        )
        if permission.resource_type == KesselResourceTypes.HOST:
            return True, None
        else:
            return False, None

    if len(ids) > 0:
        if permission.write_operation:
            # Write specific object(s) by id(s)
            logger.debug("get_kessel_filter: checking write permission for specific IDs via check_for_update")
            result, unauthorized_ids = kessel_client.check_for_update(current_identity, permission, ids)
            logger.debug(
                f"get_kessel_filter: check_for_update result={result}",
                extra={"unauthorized_ids": unauthorized_ids},
            )
            if result:
                return True, None
            else:
                # Return unauthorized IDs so the caller can include them in the error response
                return False, {"unauthorized_ids": unauthorized_ids}
        else:
            # Read specific object(s) by id(s)
            logger.debug("get_kessel_filter: checking read permission for specific IDs via check")
            result, unauthorized_ids = kessel_client.check(current_identity, permission, ids)
            logger.debug(
                f"get_kessel_filter: check result={result}",
                extra={"unauthorized_ids": unauthorized_ids},
            )
            if result:
                return True, None  # No need to apply a filter - the objects are authorized
            else:
                # Return unauthorized IDs so the caller can include them in the error response
                # Note: this is a potential departure from current behavior where an attempt to
                # request multiple objects by id will return all accessible objects, ignoring inaccessible ones.
                return False, {"unauthorized_ids": unauthorized_ids}

    # No ids passed, operate on many objects not by ids
    relation = permission.workspace_permission
    logger.debug(
        "get_kessel_filter: no specific IDs, calling ListAllowedWorkspaces",
        extra={"relation": relation},
    )
    workspaces = kessel_client.ListAllowedWorkspaces(current_identity, relation)
    logger.debug(
        "get_kessel_filter: ListAllowedWorkspaces result",
        extra={"workspaces_count": len(workspaces), "workspaces": workspaces[:10] if workspaces else []},
    )
    # NOTE: this won't work for checks that require a permission to be unfiltered
    # Ex: some org-level permissions OR permissions like add group (which we may not need to handle)
    if len(workspaces) == 0:
        logger.warning(
            "get_kessel_filter: no allowed workspaces returned, denying access",
            extra={
                "identity_type": current_identity.identity_type,
                "org_id": current_identity.org_id,
                "relation": relation,
            },
        )
        return False, None
    else:
        return True, {"groups": workspaces}


def _check_resource_exists(resource_type: KesselResourceType, ids: list[str]) -> bool:
    """
    Check if a resource exists in the database.

    Args:
        resource_type: The Kessel resource type
        ids: List of resource IDs to check

    Returns:
        True if all resources exist, False otherwise
    """
    from lib.group_repository import get_groups_by_id_list_from_db
    from lib.host_repository import find_existing_hosts_by_id_list

    if not ids:
        return True

    current_identity = get_current_identity()

    # Check based on resource type
    if resource_type.name == "host":
        # Check if all hosts exist
        return len(find_existing_hosts_by_id_list(current_identity, ids)) == len(ids)
    elif resource_type.name == "workspace":
        # Check if all groups/workspaces exist
        return len(get_groups_by_id_list_from_db(ids, current_identity.org_id)) == len(ids)
    else:
        # For other resource types, we can't check existence, so return True
        # (assume they exist to preserve original 403 behavior)
        return True


def rbac(resource_type: RbacResourceType, required_permission: RbacPermission, permission_base: str = "inventory"):
    def other_func(func):
        @wraps(func)
        def modified_func(*args, **kwargs):
            # If the API is in read-only mode and this is a Write endpoint, abort with HTTP 503.
            if required_permission == RbacPermission.WRITE and get_flag_value(FLAG_INVENTORY_API_READ_ONLY):
                abort(503, "Inventory API is currently in read-only mode.")

            if inventory_config().bypass_rbac:
                return func(*args, **kwargs)

            current_identity = get_current_identity()

            request_headers = _build_rbac_request_headers()

            allowed = None
            rbac_filter = None

            allowed, rbac_filter = get_rbac_filter(
                resource_type, required_permission, current_identity, request_headers, permission_base
            )

            if allowed:
                if rbac_filter:
                    return partial(func, rbac_filter=rbac_filter)(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            else:
                abort(HTTPStatus.FORBIDDEN)

        return modified_func

    return other_func


def access(permission: KesselPermission, id_param: str = ""):
    def other_func(func):
        sig = inspect.signature(func)

        @wraps(func)
        def modified_func(*args, **kwargs):
            # If the API is in read-only mode and this is a Write endpoint, abort with HTTP 503.
            if permission.write_operation and get_flag_value(FLAG_INVENTORY_API_READ_ONLY):
                abort(503, "Inventory API is currently in read-only mode.")

            if inventory_config().bypass_rbac:
                return func(*args, **kwargs)

            current_identity = get_current_identity()

            request_headers = _build_rbac_request_headers()

            allowed = None
            rbac_filter = None
            ids = []
            # Extract resource IDs if an id_param is provided
            if id_param:
                ids = permission.resource_type.get_resource_id(kwargs, id_param)

            if get_flag_value(
                FLAG_INVENTORY_KESSEL_PHASE_1
            ):  # Workspace permissions aren't part of HBI in V2, fallback to rbac for now.
                kessel_client = get_kessel_client(current_app)
                allowed, rbac_filter = get_kessel_filter(kessel_client, current_identity, permission, ids)
            else:
                allowed, rbac_filter = get_rbac_filter(
                    permission.resource_type.v1_type,
                    permission.v1_permission,
                    current_identity,
                    request_headers,
                    permission.resource_type.v1_app,
                )

            if allowed:
                if rbac_filter and "rbac_filter" in sig.parameters:
                    kwargs["rbac_filter"] = rbac_filter
                return func(*args, **kwargs)
            else:
                # When permission is denied and we have an id_param, check if the resource exists
                # If it doesn't exist, return 404 instead of 403
                if id_param and ids and not _check_resource_exists(permission.resource_type, ids):
                    # Include unauthorized IDs in the JSON response if available
                    unauthorized_ids = rbac_filter.get("unauthorized_ids", []) if rbac_filter else []
                    resource_name = permission.resource_type.name
                    raise IdsNotFoundError(resource_name, unauthorized_ids if unauthorized_ids else None)
                abort(HTTPStatus.FORBIDDEN)

        return modified_func

    return other_func


def rbac_group_id_check(rbac_filter: dict, requested_ids: set) -> None:
    if rbac_filter and "groups" in rbac_filter and (disallowed_ids := requested_ids.difference(rbac_filter["groups"])):
        # id check is only called before writing to groups, permission so far is always the same
        required_permission = "inventory:groups:write"
        joined_ids = ", ".join(disallowed_ids)
        rbac_group_permission_denied(logger, joined_ids, required_permission)
        abort(
            HTTPStatus.FORBIDDEN,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        )


def post_rbac_workspace(name) -> UUID | None:
    if inventory_config().bypass_kessel:
        return None

    rbac_endpoint = get_rbac_v2_url(endpoint="workspaces/")
    request_headers = _build_rbac_request_headers(request.headers[IDENTITY_HEADER], threadctx.request_id)
    request_data = {"name": name}

    resp_data = _execute_rbac_http_request(
        method="POST",
        rbac_endpoint=rbac_endpoint,
        request_headers=request_headers,
        request_data=request_data,
    )

    if resp_data is None:
        return None

    try:
        return UUID(resp_data["id"])
    except (KeyError, ValueError, TypeError) as e:
        rbac_failure(logger, e)
        abort(503, "Failed to parse RBAC response, request cannot be fulfilled")
        return None  # Satisfy mypy


def rbac_create_ungrouped_hosts_workspace(identity: Identity) -> UUID | None:
    # Creates a new "ungrouped" workspace via the RBAC API, and returns its ID.
    # If not using Kessel, returns None, so the DB will automatically generate the group ID.
    if inventory_config().bypass_kessel:
        return None

    # Get HBI's RBAC PSK from the config
    psk = inventory_config().rbac_psk
    request_headers = {
        "X-RH-RBAC-PSK": psk,
        "X-RH-RBAC-ORG-ID": identity.org_id,
        "X-RH-RBAC-CLIENT-ID": "inventory",
    }

    resp_data = rbac_get_request_using_endpoint_and_headers(get_rbac_private_url(), request_headers)

    try:
        workspace_id = resp_data["id"]
    except KeyError as e:
        rbac_failure(logger, e)
        abort(503, "Failed to parse RBAC response, request cannot be fulfilled")

    return workspace_id


def delete_rbac_workspace(workspace_id: str):
    if inventory_config().bypass_kessel:
        return True

    rbac_endpoint = _get_rbac_workspace_url(workspace_id)
    request_headers = _build_rbac_request_headers()

    _execute_rbac_http_request(
        method="DELETE",
        rbac_endpoint=rbac_endpoint,
        request_headers=request_headers,
        skip_not_found=True,  # 404s should raise ResourceNotFoundException for graceful handling
    )


def patch_rbac_workspace(workspace_id: str, name: str | None = None) -> None:
    if inventory_config().bypass_kessel:
        return None

    rbac_endpoint = _get_rbac_workspace_url(workspace_id)
    request_headers = _build_rbac_request_headers()

    request_data = {}
    if name is not None:
        request_data.update({"name": name})

    _execute_rbac_http_request(
        method="PATCH",
        rbac_endpoint=rbac_endpoint,
        request_headers=request_headers,
        request_data=request_data,
    )


def get_rbac_default_workspace() -> UUID | None:
    if inventory_config().bypass_kessel:
        return None

    response = rbac_get_request_using_endpoint_and_headers(
        get_rbac_v2_url(endpoint="workspaces/"), _build_rbac_request_headers(), {"limit": 1, "type": "default"}
    )
    data = response["data"] if response else None
    return data[0]["id"] if data and len(data) > 0 else None


def get_rbac_workspaces(
    name: str | None,
    page: int,
    per_page: int,
    group_type: str | None,
    order_by: str | None = None,
    order_how: str | None = None,
) -> tuple[list[dict], int] | None:
    """
    Query workspaces from RBAC v2 API with filtering, pagination, and sorting.

    Args:
        name: Filter by workspace name (partial match)
        page: int,
        per_page: Items per page
        group_type: Filter by workspace type
            - standard: User-created groups (default)
            - ungrouped-hosts: Ungrouped hosts workspace
            - all: All workspace types (includes standard, ungrouped-hosts, root, default)
        order_by: Sort field - supported values: 'id', 'name', 'created', 'modified', 'type'
        order_how: Sort direction ('ASC' or 'DESC')

    Returns:
        Tuple of (workspace_list, total_count)

    Raises:
        HTTPException: HTTP 503 if RBAC service returns malformed response

    Note:
        RHCLOUD-42653 has been resolved. RBAC v2 API now supports ordering
        by the following fields: id, name, created, modified, type.

        RBAC v2 filtering: This function queries the RBAC v2 workspace API using the
        user's identity header. The RBAC v2 service automatically filters results based
        on the user's permissions, so no additional client-side filtering is needed.
    """
    if inventory_config().bypass_rbac:
        # When RBAC is bypassed (e.g., in test environments), return empty results
        # This allows the feature flag to be enabled without errors in non-production environments
        return [], 0

    # sample RBAC request: console.redhat.com/api/rbac/v2/workspaces/?limit=10&offset=0&type=standard&name=my_group

    query_params = {}
    if name:
        query_params["name"] = name
    if group_type:
        query_params["type"] = group_type
    if page and per_page:
        # Convert page to offset (page is 1-based, offset is 0-based)
        offset = (page - 1) * per_page
        query_params["offset"] = str(offset)
        query_params["limit"] = str(per_page)

    if order_by and order_by != "host_count":
        # Map API field names to RBAC v2 workspace API field names
        # The API uses "updated" for consistency with existing contracts,
        # but RBAC v2 workspace API uses "modified" as the field name
        field_mapping = {
            "updated": "modified",
            "created": "created",
            "name": "name",
            "type": "type",
        }
        rbac_order_by = field_mapping.get(order_by, order_by)
        query_params["order_by"] = rbac_order_by

        if order_how:
            query_params["order_how"] = order_how.upper()  # Ensure uppercase (ASC/DESC)

    rbac_endpoint = _get_rbac_workspace_url(query_params=query_params)
    request_headers = _build_rbac_request_headers(request.headers[IDENTITY_HEADER], threadctx.request_id)

    # Query params already encoded in rbac_endpoint URL, don't pass them again
    response = get_rbac_workspace_using_endpoint_and_headers(None, rbac_endpoint, request_headers)

    # Handle missing keys safely with type validation
    if not response:
        logger.warning("Empty response received from RBAC workspace endpoint")
        return [], 0

    # Extract data with safe key access and type validation
    data = response.get("data", [])
    if not isinstance(data, list):
        error_msg = f"RBAC service returned malformed response: expected 'data' to be a list, got {type(data)}"
        logger.error(error_msg)
        abort(HTTPStatus.SERVICE_UNAVAILABLE, error_msg)

    # RBAC v2 Note: We do NOT apply rbac_filter here because the RBAC v2 workspace API
    # already filters results based on the user's identity header. The user only receives
    # workspaces they have permission to access. Applying an additional RBAC v1 filter
    # would be redundant and could cause inconsistencies during the RBAC v1 to v2 migration.

    count = response.get("meta", {}).get("count", 0)

    return data, count


def get_rbac_workspace_by_id(workspace_id: str) -> dict[str, Any] | None:
    """
    Fetch a single workspace from RBAC v2 API by ID.

    Args:
        workspace_id: UUID of the workspace to fetch

    Returns:
        dict: Workspace object from RBAC v2 API, or None if bypass_kessel is enabled

    Raises:
        ResourceNotFoundException: If workspace not found (404)
        HTTPException: For other RBAC v2 API errors (5xx, etc.)

    Example:
        workspace = get_rbac_workspace_by_id("019a5ae6-69bf-7323-bc60-f075715034c8")
        # Returns: {"id": "019a5ae6-...", "name": "Production", ...}
    """
    if inventory_config().bypass_kessel:
        return None

    # Delegate to batch API with single ID
    workspaces = get_rbac_workspaces_by_ids([workspace_id])
    return workspaces[0] if workspaces else None


def get_rbac_workspaces_by_ids(workspace_ids: list[str]) -> list[dict[str, Any]]:
    """
    Fetch multiple workspaces from RBAC v2 API by ID list.

    This function makes a batch API call to fetch multiple workspaces in a single request.
    Previously blocked by RHCLOUD-43362, now implemented with batch workspace fetch support.

    Args:
        workspace_ids: List of workspace UUIDs to fetch

    Returns:
        list[dict]: List of workspace objects from RBAC v2 API

    Raises:
        ResourceNotFoundException: If one or more workspaces not found
        HTTPException: For other RBAC v2 API errors (5xx, etc.)

    Example:
        workspaces = get_rbac_workspaces_by_ids(["uuid1", "uuid2", "uuid3"])
        # Returns: [{"id": "uuid1", ...}, {"id": "uuid2", ...}, {"id": "uuid3", ...}]
    """
    if inventory_config().bypass_kessel:
        return []

    # Build query parameter string with multiple IDs
    # Format: ?id=uuid1,uuid2,uuid3
    ids_param = ",".join(workspace_ids)
    rbac_endpoint = _get_rbac_workspace_url(query_params={"id": ids_param})
    request_headers = _build_rbac_request_headers()

    response = _execute_rbac_http_request(
        method="GET",
        rbac_endpoint=rbac_endpoint,
        request_headers=request_headers,
        skip_not_found=False,  # Don't skip 404s, we want to know if any are missing
    )

    # Extract workspaces from response
    workspaces = response.get("data", []) if response else []

    # Verify all requested workspaces were found
    found_ids = {ws["id"] for ws in workspaces}
    requested_ids = set(workspace_ids)

    if found_ids != requested_ids:
        missing_ids = requested_ids - found_ids
        raise ResourceNotFoundException(f"Workspaces not found: {', '.join(missing_ids)}")

    return workspaces


def get_rbac_workspace_using_endpoint_and_headers(
    request_data: dict | None, rbac_endpoint: str, request_headers: dict
) -> dict[Any, Any] | None:
    return _execute_rbac_http_request(
        method="GET",
        rbac_endpoint=rbac_endpoint,
        request_headers=request_headers,
        request_params=request_data,  # For GET requests, use request_params instead of request_data
    )
