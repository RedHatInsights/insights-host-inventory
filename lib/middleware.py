from functools import partial
from functools import wraps
from typing import Dict
from typing import List
from typing import Set
from typing import Tuple
from uuid import UUID

from app_common_python import LoadedConfig
from flask import abort
from flask import g
from flask import request
from flask_api import status
from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from api.metrics import outbound_http_response_time
from app import IDENTITY_HEADER
from app import inventory_config
from app import RbacPermission
from app import RbacResourceType
from app import REQUEST_ID_HEADER
from app.auth import get_current_identity
from app.auth.identity import IdentityType
from app.instrumentation import rbac_failure
from app.instrumentation import rbac_permission_denied
from app.logging import get_logger


logger = get_logger(__name__)

RBAC_ROUTE = "/api/rbac/v1/access/?application="
CHECKED_TYPE = IdentityType.USER
RETRY_STATUSES = [500, 502, 503, 504]

outbound_http_metric = outbound_http_response_time.labels("rbac")


class RbacIdFilter:
    def __init__(self, resource: RbacResourceType, id_set: Set[str]) -> None:
        self.resource = resource
        self.id_set = id_set


class RbacFilter:
    # For quicker and easier access, otherPermissions is a dict with a format like this:
    # {
    #   "inventory:groups:read": <RbacIdFilter>,
    #   "inventory:hosts:write": <RbacIdFilter>,
    #   ...etc...
    # }
    def __init__(
        self,
        resource: RbacResourceType = RbacResourceType.HOSTS,
        permission: RbacPermission = RbacPermission.READ,
        filter_by: RbacIdFilter = None,
        other_permissions: Dict[str, RbacIdFilter] = {},
    ) -> None:
        # The resource and permission this filter applies to (e.g. hosts:read)
        self.resource = resource
        self.permission = permission
        # The filter being applied (RBAC attributeFilter, e.g. list of group ID)
        self.filter_by = filter_by
        # Extra RBAC permission data needed by certain endpoints
        self.other_permissions = other_permissions


def get_rbac_url(app: str) -> str:
    return inventory_config().rbac_endpoint + RBAC_ROUTE + app


def tenant_translator_url() -> str:
    return inventory_config().tenant_translator_url


def get_rbac_permissions(app):
    request_header = {
        IDENTITY_HEADER: request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request.headers.get(REQUEST_ID_HEADER),
    }

    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(get_rbac_url(app), HTTPAdapter(max_retries=retry_config))

    try:
        with outbound_http_metric.time():
            rbac_response = request_session.get(
                url=get_rbac_url(app),
                headers=request_header,
                timeout=inventory_config().rbac_timeout,
                verify=LoadedConfig.tlsCAPath,
            )
    except Exception as e:
        rbac_failure(logger, e)
        abort(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")
    finally:
        request_session.close()

    resp_data = rbac_response.json()
    logger.debug("Fetched RBAC Data", extra=resp_data)

    return resp_data["data"]


def _validate_attribute_filter(attributeFilter: dict) -> None:
    if attributeFilter.get("key") != "group.id":
        abort(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Invalid value for attributeFilter.key in RBAC response.",
        )
    elif attributeFilter.get("operation") != "in":
        abort(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Invalid value for attributeFilter.operation in RBAC response.",
        )
    elif not isinstance(attributeFilter["value"], list):
        abort(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Did not receive a list for attributeFilter.value in RBAC response.",
        )
    try:
        # Validate that each value is in correct UUID format.
        for gid in attributeFilter["value"]:
            if gid is not None:
                UUID(gid)
    except ValueError:
        abort(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Received invalid UUIDs for attributeFilter.value in RBAC response.",
        )


def _get_attribute_filter_value(rbac_permission) -> Set[str]:
    # Get the list of allowed Group IDs from the attribute filter.
    attribute_filter_value = set()
    for resourceDefinition in rbac_permission["resourceDefinitions"]:
        if "attributeFilter" in resourceDefinition:
            _validate_attribute_filter(resourceDefinition["attributeFilter"])
            attribute_filter_value.update(resourceDefinition["attributeFilter"]["value"])

    return attribute_filter_value


def _parse_rbac_permission_string(rbac_permission: str) -> Tuple[str, RbacResourceType, RbacPermission]:
    permission_split = rbac_permission.split(":")
    return (permission_split[0], RbacResourceType(permission_split[1]), RbacPermission(permission_split[2]))


def _get_allowed_ids(
    rbac_data, permission_base: str, resource_type: RbacResourceType, required_permission: RbacPermission
) -> Tuple[Set[str], bool]:
    match_found = False  # Whether or not a matching permission was found
    allowed_group_ids = set()  # The list of group IDs that access is restricted to (if any)

    for rbac_permission in rbac_data:
        if (
            rbac_permission["permission"]  # inventory:*:*
            == f"{permission_base}:{RbacResourceType.ALL.value}:{RbacPermission.ADMIN.value}"
            or rbac_permission["permission"]  # inventory:{type}:*
            == f"{permission_base}:{resource_type.value}:{RbacPermission.ADMIN.value}"
            or rbac_permission["permission"]  # inventory:*:(read | write)
            == f"{permission_base}:{RbacResourceType.ALL.value}:{required_permission.value}"
            or rbac_permission["permission"]  # inventory:{type}:(read | write)
            == f"{permission_base}:{resource_type.value}:{required_permission.value}"
        ):
            match_found = True

            # Get the list of allowed Group IDs from the attribute filter.
            attribute_filter_value = _get_attribute_filter_value(rbac_permission)

            if attribute_filter_value:
                # If the RBAC permission is applicable and is limited to specific group IDs,
                # add that list of group IDs to the list of allowed group IDs.
                allowed_group_ids.update(attribute_filter_value)
            else:
                # If any applicable RBAC permission exists and is NOT limited to specific group IDs,
                # we should return an empty list to imply that it's not limited to specific IDs.
                return set(), True

    return allowed_group_ids, match_found


def rbac(
    resource_type: RbacResourceType,
    required_permission: RbacPermission,
    permission_base: str = "inventory",
    additional_permissions: List[str] = [],
):
    def other_func(func):
        @wraps(func)
        def modified_func(*args, **kwargs):
            current_identity = get_current_identity()
            if inventory_config().bypass_rbac or current_identity.identity_type != CHECKED_TYPE:
                return partial(
                    func,
                    rbac_filter=RbacFilter(
                        resource_type,
                        required_permission,
                        None,
                        {},
                    ),
                )(*args, **kwargs)

            # track that RBAC is being used to control access
            g.access_control_rule = "RBAC"
            logger.debug("access_control_rule set")

            rbac_data = get_rbac_permissions(permission_base)

            # TODO: Remove this workaround after RHCLOUD-27511 is implemented.
            # If the required permission is RBAC admin, we can check the Identity instead.
            if (
                permission_base == "rbac"
                and current_identity.identity_type == IdentityType.USER
                and current_identity.user.get("is_org_admin")
            ):
                return func(*args, **kwargs)

            # Get the allowed IDs for the required permission
            allowed_group_ids, is_allowed = _get_allowed_ids(
                rbac_data, permission_base, resource_type, required_permission
            )

            # Get the allowed IDs for any additional permissions requested
            other_permissions = {}
            for additional_permission in additional_permissions:
                additional_ids, _ = _get_allowed_ids(
                    rbac_data, *(_parse_rbac_permission_string(additional_permission))
                )
                other_permissions[additional_permission] = RbacIdFilter(RbacResourceType.GROUPS, additional_ids)

            # If all applicable permissions are restricted to specific groups,
            # call the endpoint with the RBAC filtering data.
            if is_allowed:
                rbac_filter = RbacFilter(
                    resource_type,
                    required_permission,
                    RbacIdFilter(RbacResourceType.GROUPS, allowed_group_ids) if allowed_group_ids else None,
                    other_permissions,
                )

                return partial(func, rbac_filter=rbac_filter)(*args, **kwargs)
            else:
                rbac_permission_denied(logger, required_permission.value, rbac_data)
                abort(status.HTTP_403_FORBIDDEN)

        return modified_func

    return other_func


def rbac_group_id_check(rbac_filter: RbacFilter, requested_ids: set) -> None:
    if rbac_filter.filter_by and rbac_filter.filter_by.resource == RbacResourceType.GROUPS:
        # Find the IDs that are in requested_ids but not rbac_filter
        disallowed_ids = requested_ids.difference(rbac_filter.filter_by.id_set)
        if len(disallowed_ids) > 0:
            joined_ids = ", ".join(disallowed_ids)
            abort(status.HTTP_403_FORBIDDEN, f"You do not have access to the the following groups: {joined_ids}")
