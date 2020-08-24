from enum import Enum
from functools import wraps

from flask import abort
from flask import request
from flask_api import status
from requests import exceptions
from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from app import IDENTITY_HEADER
from app import inventory_config
from app import REQUEST_ID_HEADER
from app import UNKNOWN_REQUEST_ID_VALUE
from app.auth import current_identity
from app.instrumentation import rbac_failure
from app.instrumentation import rbac_permission_denied
from app.logging import get_logger


logger = get_logger(__name__)

ROUTE = "/api/rbac/v1/access/?application=inventory"
ALLOWED_TYPE = "User"

class Permission(Enum):
    READ = "inventory:hosts:read"
    WRITE = "inventory:hosts:write"
    ADMIN = "inventory:*:*"
    HOSTS_ALL = "inventory:hosts:*"


def rbac_url():
    return inventory_config().rbac_endpoint + ROUTE


def get_rbac_permissions():
    request_header = {
        IDENTITY_HEADER: request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request.headers.get(REQUEST_ID_HEADER, UNKNOWN_REQUEST_ID_VALUE),
    }

    request_session = Session()
    retry_config = Retry(total=inventory_config().rbac_retries, backoff_factor=1, status_forcelist=[401, 404, 500])
    request_session.mount(rbac_url(), HTTPAdapter(max_retries=retry_config))

    try:
        rbac_response = request_session.get(
            url=rbac_url(), headers=request_header, timeout=inventory_config().rbac_timeout
        )
    except exceptions.RetryError as e:
        rbac_failure(logger, "max_retry", e)
        abort(503, "Error fetching RBAC data, request cannot be fulfilled")
    except Exception as e:
        rbac_failure(logger, "fetch", e)
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
            if not inventory_config().rbac_enforced:
                return func(*args, **kwargs)

            if current_identity.identity_type != ALLOWED_TYPE:
                return func(*args, **kwargs)

            rbac_data = get_rbac_permissions()

            for rbac_permission in rbac_data:
                if (
                    rbac_permission["permission"] == Permission.ADMIN.value
                    or rbac_permission["permission"] == Permission.HOSTS_ALL.value
                    or rbac_permission["permission"] == required_permission.value
                ):
                    return func(*args, **kwargs)

            rbac_permission_denied(logger, required_permission.value, rbac_data)
            abort(status.HTTP_403_FORBIDDEN)

        return modified_func

    return other_func
