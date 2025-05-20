from __future__ import annotations

from functools import partial
from functools import wraps
from http import HTTPStatus
from json import JSONDecodeError
from typing import Dict, Tuple
from uuid import UUID

from app_common_python import LoadedConfig
from flask import abort
from flask import g
from flask import request
from flask import current_app
from requests import Session
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
from requests.packages.urllib3.util.retry import Retry

from api.metrics import outbound_http_response_time
from app import IDENTITY_HEADER
from app import REQUEST_ID_HEADER
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.auth.identity import from_auth_header
from app.auth.identity import to_auth_header
from app.common import inventory_config
from app.instrumentation import rbac_failure
from app.instrumentation import rbac_group_permission_denied
from app.instrumentation import rbac_permission_denied
from app.logging import get_logger
from app.logging import threadctx
from lib.feature_flags import FLAG_INVENTORY_API_READ_ONLY, FLAG_INVENTORY_KESSEL_HOST_MIGRATION
from lib.feature_flags import get_flag_value
from lib.kessel import get_kessel_client, Kessel

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


def get_rbac_private_url() -> str:
    return inventory_config().rbac_endpoint + RBAC_PRIVATE_UNGROUPED_ROUTE


def tenant_translator_url() -> str:
    return inventory_config().tenant_translator_url


def _build_rbac_request_headers(identity_header: str | None = None, request_id_header: str | None = None) -> dict:
    request_headers = {
        IDENTITY_HEADER: identity_header or request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request_id_header or request.headers.get(REQUEST_ID_HEADER),
    }
    return request_headers


def rbac_get_request_using_endpoint_and_headers(rbac_endpoint: str, request_headers: dict):
    if inventory_config().bypass_rbac:
        return None

    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(rbac_endpoint, HTTPAdapter(max_retries=retry_config))

    try:
        with outbound_http_response_time.labels("rbac").time():
            rbac_response = request_session.get(
                url=rbac_endpoint,
                headers=request_headers,
                timeout=inventory_config().rbac_timeout,
                verify=LoadedConfig.tlsCAPath,
            )
    except Exception as e:
        rbac_failure(logger, e)
        abort(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")
    finally:
        request_session.close()

    try:
        resp_data = rbac_response.json()
    except JSONDecodeError as e:
        rbac_failure(logger, e)
        abort(503, "Failed to parse RBAC response, request cannot be fulfilled")
    finally:
        request_session.close()

    return resp_data


def get_rbac_permissions(app: str, request_header: dict):
    resp_data = rbac_get_request_using_endpoint_and_headers(get_rbac_url(app), request_header)
    logger.debug("Fetched RBAC Data", extra=resp_data)
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
    if "attributeFilter" in resource_definition:
        if resource_definition["attributeFilter"].get("key") != "group.id":
            abort(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Invalid value for attributeFilter.key in RBAC response.",
            )
        elif resource_definition["attributeFilter"].get("operation") != "in":
            abort(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Invalid value for attributeFilter.operation in RBAC response.",
            )
        elif not isinstance(resource_definition["attributeFilter"]["value"], list):
            abort(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Did not receive a list for attributeFilter.value in RBAC response.",
            )
        else:
            # Validate that all values in the filter are UUIDs.
            group_list = resource_definition["attributeFilter"]["value"]
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
    else:
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
    kessel_client: Kessel,
    current_identity: Identity,
    application: str,
    resource_type: RbacResourceType,
    verb: RbacPermission,
) -> Tuple[bool, Dict[str, Any]]:
    if current_identity.identity_type not in CHECKED_TYPES:
        if resource_type == RbacResourceType.HOSTS:
            return True, None
        else:
            return False, None
        
    relation = f"{application}_{kessel_type(resource_type)}_{kessel_verb(verb)}"

    workspaces = kessel_client.ListAllowedWorkspaces(current_identity, relation)

    # TODO: this won't work for org-level permissions OR permissions like add group (which we may not need to handle) that require a permission to be unfiltered
    if len(workspaces) == 0:
        return False, None
    else:
        return True, {"groups": workspaces}

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
            if get_flag_value(FLAG_INVENTORY_KESSEL_HOST_MIGRATION):
                kessel_client = get_kessel_client(current_app)
                allowed, rbac_filter = get_kessel_filter(kessel_client, current_identity, permission_base, resource_type, required_permission)
            else:
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


def rbac_group_id_check(rbac_filter: dict, requested_ids: set) -> None:
    if rbac_filter and "groups" in rbac_filter:
        # Find the IDs that are in requested_ids but not rbac_filter
        disallowed_ids = requested_ids.difference(rbac_filter["groups"])
        if len(disallowed_ids) > 0:
            # id check is only called before writing to groups, permission so far is always the same
            required_permission = "inventory:groups:write"
            joined_ids = ", ".join(disallowed_ids)
            rbac_group_permission_denied(logger, joined_ids, required_permission)
            abort(HTTPStatus.FORBIDDEN, f"You do not have access to the the following groups: {joined_ids}")


def _temp_add_org_admin_user_identity(identity_header: str) -> str:
    identity = from_auth_header(identity_header)
    if inventory_config().rbac_v2_force_org_admin and identity.identity_type == IdentityType.USER:
        if hasattr(identity, "user"):
            identity.user["is_org_admin"] = True
        else:
            identity.user = {"username": "hbi-override", "is_org_admin": True}
        return to_auth_header(identity)

    return identity_header


def post_rbac_workspace(name) -> UUID | None:
    if inventory_config().bypass_rbac:
        return None

    rbac_endpoint = get_rbac_v2_url(endpoint="workspaces/")
    identity_header = _temp_add_org_admin_user_identity(request.headers[IDENTITY_HEADER])
    request_headers = _build_rbac_request_headers(identity_header, threadctx.request_id)
    request_data = {"name": name}

    return post_rbac_workspace_using_endpoint_and_headers(request_data, rbac_endpoint, request_headers)


def post_rbac_workspace_using_endpoint_and_headers(
    request_data: dict | None, rbac_endpoint: str, request_headers: dict
) -> UUID | None:
    if inventory_config().bypass_rbac:
        return None

    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(rbac_endpoint, HTTPAdapter(max_retries=retry_config))

    try:
        with outbound_http_response_time.labels("rbac").time():
            rbac_response = request_session.post(
                url=rbac_endpoint,
                headers=request_headers,
                json=request_data,
                timeout=inventory_config().rbac_timeout,
                verify=LoadedConfig.tlsCAPath,
            )
            rbac_response.raise_for_status()
    except HTTPError as e:
        status_code = e.response.status_code
        if 400 <= status_code < 500:
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
        error_message = f"Unexpected error: {e.__class__.__name__}: {str(e)}"
        logger.error(error_message)
        abort(500, error_message)
    finally:
        request_session.close()

    workspace_id = None
    try:
        resp_data = rbac_response.json()
        workspace_id = resp_data["id"]
        logger.debug("POSTED RBAC Data", extra=resp_data)
    except (JSONDecodeError, KeyError) as e:
        rbac_failure(logger, e)
        abort(503, "Failed to parse RBAC response, request cannot be fulfilled")
    finally:
        request_session.close()

    return workspace_id


def rbac_create_ungrouped_hosts_workspace(identity: Identity) -> UUID | None:
    # Creates a new "ungrouped" workspace via the RBAC API, and returns its ID.
    # If not using RBAC, returns None, so the DB will automatically generate the group ID.
    if inventory_config().bypass_rbac:
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


def delete_rbac_workspace(workspace_id):
    if inventory_config().bypass_rbac:
        return None

    workspace_endpoint = f"workspaces/{workspace_id}/"
    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(get_rbac_v2_url(endpoint=workspace_endpoint), HTTPAdapter(max_retries=retry_config))
    request_headers = _build_rbac_request_headers()

    try:
        with outbound_http_response_time.labels("rbac").time():
            request_session.delete(
                url=get_rbac_v2_url(endpoint=workspace_endpoint),
                headers=request_headers,
                timeout=inventory_config().rbac_timeout,
                verify=LoadedConfig.tlsCAPath,
            )
    except Exception as e:
        rbac_failure(logger, e)
        abort(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")
    finally:
        request_session.close()


def patch_rbac_workspace(workspace_id: str, name: str | None = None) -> None:
    if inventory_config().bypass_rbac:
        return None

    workspace_endpoint = f"workspaces/{workspace_id}/"
    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(get_rbac_v2_url(endpoint=workspace_endpoint), HTTPAdapter(max_retries=retry_config))
    request_headers = _build_rbac_request_headers()

    request_data = {}
    if name is not None:
        request_data.update({"name": name})

    try:
        with outbound_http_response_time.labels("rbac").time():
            request_session.patch(
                url=get_rbac_v2_url(endpoint=workspace_endpoint),
                headers=request_headers,
                json=request_data,
                timeout=inventory_config().rbac_timeout,
                verify=LoadedConfig.tlsCAPath,
            )
    except Exception as e:
        rbac_failure(logger, e)
        abort(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")
    finally:
        request_session.close()
