from base64 import b64decode
from functools import wraps
from json import loads

from flask import abort
from flask import request
from flask_api import status
from requests import get

from app import IDENTITY_HEADER
from app import inventory_config
from app.logging import get_logger


logger = get_logger(__name__)


def get_identity_type(identity_header):
    decoded_header = b64decode(identity_header)
    identity_dict = loads(decoded_header)
    return identity_dict["identity"]["type"]


def rbac_url():
    route = "/api/rbac/v1/access/?application=inventory"
    return inventory_config().rbac_endpoint + route


def get_rbac_permissions():
    request_header = {IDENTITY_HEADER: request.headers[IDENTITY_HEADER]}

    rbac_response = get(rbac_url(), headers=request_header)
    status = rbac_response.status_code
    if status != 200:
        logger.error("RBAC returned status: %s", status)
        abort(500, "Error Fetching RBAC Data, Request Cannot be fulfilled")

    resp_data = loads(rbac_response.content.decode("utf-8"))
    logger.debug("Fetched RBAC Permissions %s", resp_data)

    return resp_data["data"]


def rbac(requested_permission):
    def other_func(func):
        @wraps(func)
        def modified_func(*args, **kwargs):
            result = func(*args, **kwargs)

            if not inventory_config().rbac_enforced:
                return result

            if get_identity_type(request.headers[IDENTITY_HEADER]) == "System":
                return result

            rbac_data = get_rbac_permissions()

            for rbac_permission in rbac_data:
                if (
                    rbac_permission["permission"] == "inventory:*:*"
                    or rbac_permission["permission"] == "inventory:hosts:*"
                    or rbac_permission["permission"] == requested_permission
                ):
                    return result

            abort(status.HTTP_403_FORBIDDEN)

        return modified_func

    return other_func
