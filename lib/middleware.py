import json
from functools import wraps

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
from app import Permission
from app import REQUEST_ID_HEADER
from app import UNKNOWN_REQUEST_ID_VALUE
from app.auth import get_current_identity
from app.auth.identity import IdentityType
from app.exceptions import InventoryException
from app.instrumentation import rbac_failure
from app.instrumentation import rbac_permission_denied
from app.instrumentation import tenant_translator_failure
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
        REQUEST_ID_HEADER: request.headers.get(REQUEST_ID_HEADER, UNKNOWN_REQUEST_ID_VALUE),
    }

    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(rbac_url(), HTTPAdapter(max_retries=retry_config))

    try:
        with outbound_http_metric.time():
            rbac_response = request_session.get(
                url=rbac_url(), headers=request_header, timeout=inventory_config().rbac_timeout
            )
    except Exception as e:
        rbac_failure(logger, e)
        abort(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")
    finally:
        request_session.close()

    resp_data = rbac_response.json()
    logger.debug("Fetched RBAC Data", extra=resp_data)

    return resp_data["data"]


def rbac(required_permission):
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

            permission_type = required_permission.value.split(":")[2]

            for rbac_permission in rbac_data:
                if (
                    rbac_permission["permission"] == Permission.ADMIN.value  # inventory:*:*
                    or rbac_permission["permission"] == Permission.HOSTS_ALL.value  # inventory:hosts:*
                    or rbac_permission["permission"] == f"inventory:*:{permission_type}"  # inventory:*:(read | write)
                    or rbac_permission["permission"] == required_permission.value  # inventory:hosts:(read | write)
                ):
                    return func(*args, **kwargs)

            rbac_permission_denied(logger, required_permission.value, rbac_data)
            abort(status.HTTP_403_FORBIDDEN)

        return modified_func

    return other_func


def translate_account_to_org_id(account: str) -> str:
    # If translation is bypassed, set the org_id to None
    if inventory_config().bypass_tenant_translation:
        return None

    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_session.mount(tenant_translator_url(), HTTPAdapter(max_retries=retry_config))

    try:
        with outbound_http_metric.time():
            translator_response = request_session.post(
                url=tenant_translator_url(), timeout=inventory_config().rbac_timeout, json=[account]
            )
    except Exception as e:
        tenant_translator_failure(logger, e)
        raise InventoryException(
            title="Network Error",
            detail="Failed to reach 3scale tenant translator endpoint; request cannot be fulfilled",
        )
    finally:
        request_session.close()

    try:
        resp_data = translator_response.json()
    except json.decoder.JSONDecodeError as e:
        tenant_translator_failure(logger, e)
        raise InventoryException(
            title="Network Error",
            detail=(
                "Could not decode response body received from tenant translator endpoint "
                f"with status {translator_response.status_code}: {translator_response.content}"
            ),
        )

    return resp_data.get(account)
