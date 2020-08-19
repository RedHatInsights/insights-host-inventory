import json
from functools import wraps

import flask
from flask import request
from flask_api import status
from requests import get

from app import inventory_config
from app.logging import get_logger


logger = get_logger(__name__)


def get_rbac_permissions():
    # route = "/api/rbac/v1/access/?application=inventory"
    route = "/r/insights/platform/rbac/v1/access/?application=inventory"
    rbac_url = inventory_config().rbac_endpoint + route
    request_header = {"x-rh-identity": request.headers["x-rh-identity"]}

    with get(rbac_url, headers=request_header) as rbac_response:
        resp_data = json.loads(rbac_response.content.decode("utf-8"))
        return resp_data["data"]

    # with open("utils/rbac-mock-data/inv-read-write.json", "r") as rbac_response:
    #     resp_data = json.load(rbac_response)
    #     return resp_data["data"]


def rbac(requested_permission):
    def other_func(func):
        @wraps(func)
        def modified_func(*args, **kwargs):
            result = func(*args, **kwargs)

            if not inventory_config().rbac_enforced:
                return result

            rbac_data = get_rbac_permissions()

            logger.info("Fetched RBAC Permissions %s", rbac_data)

            for rbac_permission in rbac_data:
                if (
                    rbac_permission["permission"] == "inventory:*:*"
                    or rbac_permission["permission"] == "inventory:hosts:*"
                    or rbac_permission["permission"] == requested_permission
                ):
                    return result

            flask.abort(status.HTTP_403_FORBIDDEN)

        return modified_func

    return other_func
