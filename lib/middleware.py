from functools import partial
from functools import wraps
from http import HTTPStatus
from uuid import UUID

from app_common_python import LoadedConfig
from flask import abort
from flask import g
from flask import request
from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from api.metrics import outbound_http_response_time
from app import IDENTITY_HEADER
from app import RbacPermission
from app import RbacResourceType
from app import REQUEST_ID_HEADER
from app.auth import get_current_identity
from app.auth.identity import create_mock_identity_with_org_id
from app.auth.identity import IdentityType
from app.common import inventory_config
from app.instrumentation import rbac_failure
from app.instrumentation import rbac_group_permission_denied
from app.instrumentation import rbac_permission_denied
from app.logging import get_logger


logger = get_logger(__name__)

RBAC_ROUTE = "/api/rbac/v1/access/?application="
CHECKED_TYPES = [IdentityType.USER, IdentityType.SERVICE_ACCOUNT]
RETRY_STATUSES = [500, 502, 503, 504]

outbound_http_metric = outbound_http_response_time.labels("rbac")


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


def rbac(resource_type, required_permission, permission_base="inventory", org_id=None):
    def other_func(func):
        @wraps(func)
        def modified_func(*args, **kwargs):
            if inventory_config().bypass_rbac:
                return func(*args, **kwargs)

            if not org_id:
                current_identity = get_current_identity()
            else:
                current_identity = create_mock_identity_with_org_id(org_id)

            if current_identity.identity_type not in CHECKED_TYPES:
                if resource_type == RbacResourceType.HOSTS:
                    return func(*args, **kwargs)
                else:
                    abort(HTTPStatus.FORBIDDEN)

            # track that RBAC is being used to control access
            g.access_control_rule = "RBAC"
            logger.debug("access_control_rule set")

            rbac_data = get_rbac_permissions(permission_base)
            # rbac_data = [
            #    {
            #        "resourceDefinitions": [
            #            {
            #                "attributeFilter": {
            #                    "key": "group.id",
            #                    "value": ["ff4cc1dc-7a43-4ed7-818b-71fe857a8185"],
            #                    "operation": "in",
            #                }
            #            }
            #        ],
            #        "permission": "inventory:hosts:read",
            #    },
            #    {
            #        "resourceDefinitions": [
            #            {
            #                "attributeFilter": {
            #                    "key": "group.id",
            #                    "value": ["ff4cc1dc-7a43-4ed7-818b-71fe857a8185"],
            #                    "operation": "in",
            #                }
            #            }
            #        ],
            #        "permission": "inventory:groups:read",
            #    },
            # ]

            # Determines whether the endpoint can be accessed at all
            allowed = False
            # If populated, limits the allowed resources to specific group IDs
            allowed_group_ids = set()

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
                    # If any of the above match, the endpoint should at least be allowed.
                    allowed = True

                    # Get the list of allowed Group IDs from the attribute filter.
                    groups_attribute_filter = set()
                    for resourceDefinition in rbac_permission["resourceDefinitions"]:
                        if "attributeFilter" in resourceDefinition:
                            if resourceDefinition["attributeFilter"].get("key") != "group.id":
                                abort(
                                    HTTPStatus.SERVICE_UNAVAILABLE,
                                    "Invalid value for attributeFilter.key in RBAC response.",
                                )
                            elif resourceDefinition["attributeFilter"].get("operation") != "in":
                                abort(
                                    HTTPStatus.SERVICE_UNAVAILABLE,
                                    "Invalid value for attributeFilter.operation in RBAC response.",
                                )
                            elif not isinstance(resourceDefinition["attributeFilter"]["value"], list):
                                abort(
                                    HTTPStatus.SERVICE_UNAVAILABLE,
                                    "Did not receive a list for attributeFilter.value in RBAC response.",
                                )
                            else:
                                # Add the IDs to the filter, but validate that they're all actually UUIDs.
                                groups_attribute_filter.update(resourceDefinition["attributeFilter"]["value"])
                                try:
                                    for gid in groups_attribute_filter:
                                        if gid is not None:
                                            UUID(gid)
                                except ValueError:
                                    abort(
                                        HTTPStatus.SERVICE_UNAVAILABLE,
                                        "Received invalid UUIDs for attributeFilter.value in RBAC response.",
                                    )

                    if groups_attribute_filter:
                        # If the RBAC permission is applicable and is limited to specific group IDs,
                        # add that list of group IDs to the list of allowed group IDs.
                        allowed_group_ids.update(groups_attribute_filter)
                    else:
                        # If any applicable RBAC permission exists and is NOT limited to specific group IDs,
                        # call the usual endpoint without resource-specific access limitations.
                        return func(*args, **kwargs)

            # If all applicable permissions are restricted to specific groups,
            # call the endpoint with the RBAC filtering data.
            if allowed:
                return partial(func, rbac_filter={"groups": allowed_group_ids})(*args, **kwargs)
            else:
                rbac_permission_denied(logger, required_permission.value, rbac_data)
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
