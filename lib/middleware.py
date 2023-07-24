from functools import partial
from functools import wraps
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

ROUTE = "/api/rbac/v1/access/?application=inventory"
CHECKED_TYPE = IdentityType.USER
RETRY_STATUSES = [500, 502, 503, 504]

outbound_http_metric = outbound_http_response_time.labels("rbac")


def rbac_url():
    return inventory_config().rbac_endpoint + ROUTE


def tenant_translator_url() -> str:
    return inventory_config().tenant_translator_url


def get_rbac_permissions():
    request_header = {
        IDENTITY_HEADER: request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request.headers.get(REQUEST_ID_HEADER),
    }

    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(rbac_url(), HTTPAdapter(max_retries=retry_config))

    try:
        with outbound_http_metric.time():
            rbac_response = request_session.get(
                url=rbac_url(),
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


def rbac(resource_type, required_permission, permission_base="inventory"):
    def other_func(func):
        @wraps(func)
        def modified_func(*args, **kwargs):
            if inventory_config().bypass_rbac:
                return func(*args, **kwargs)

            if get_current_identity().identity_type != CHECKED_TYPE:
                return func(*args, **kwargs)

            # track that RBAC is being used to control access
            g.access_control_rule = "RBAC"
            logger.debug("access_control_rule set")

            rbac_data = get_rbac_permissions()

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
                                    status.HTTP_503_SERVICE_UNAVAILABLE,
                                    "Invalid value for attributeFilter.key in RBAC response.",
                                )
                            elif resourceDefinition["attributeFilter"].get("operation") != "in":
                                abort(
                                    status.HTTP_503_SERVICE_UNAVAILABLE,
                                    "Invalid value for attributeFilter.operation in RBAC response.",
                                )
                            elif not isinstance(resourceDefinition["attributeFilter"]["value"], list):
                                abort(
                                    status.HTTP_503_SERVICE_UNAVAILABLE,
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
                                        status.HTTP_503_SERVICE_UNAVAILABLE,
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
                abort(status.HTTP_403_FORBIDDEN)

        return modified_func

    return other_func


def rbac_group_id_check(rbac_filter: dict, requested_ids: set) -> None:
    if rbac_filter and "groups" in rbac_filter:
        # Find the IDs that are in requested_ids but not rbac_filter
        disallowed_ids = requested_ids.difference(rbac_filter["groups"])
        if len(disallowed_ids) > 0:
            joined_ids = ", ".join(disallowed_ids)
            abort(status.HTTP_403_FORBIDDEN, f"You do not have access to the the following groups: {joined_ids}")
