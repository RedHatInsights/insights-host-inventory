import json
from requests import get

from flask import current_app
from flask import request

from app.logging import get_logger


logger = get_logger(__name__)

read_actions = {
    "get_host_list",
    "get_host_by_id",
    "get_host_system_profile_by_id",
    "get_host_tag_count",
    "get_host_tags",
}
write_actions = {"add_host_list", "delete_by_id", "patch_by_id", "replace_facts", "merge_facts"}


def get_rbac_permissions():
    # route = "/api/rbac/v1/access/?application=inventory"
    route = "/r/insights/platform/rbac/v1/access/?application=inventory"
    rbac_url = current_app.config["INVENTORY_CONFIG"].rbac_endpoint + route
    request_header = { 'x-rh-identity': request.headers['x-rh-identity'],}

    with get(rbac_url, headers=request_header) as rbac_response:
        resp_data = json.loads(rbac_response.content.decode('utf-8'))
        print("RBAC_DATA RESPONSE", resp_data)
        return resp_data["data"]

    # with open("utils/rbac-mock-data/inv-read-write.json", "r") as rbac_response:
    #     resp_data = json.load(rbac_response)
    #     return resp_data["data"]


def check_rbac_permissions(action):
    rbac_data = get_rbac_permissions()

    logger.info("Fetched RBAC Permissions %s", rbac_data)

    for rbac_permission in rbac_data:
        _, resource, verb = rbac_permission["permission"].split(":")

        if resource == "hosts" or resource == "*":
            if verb == "read" and action in read_actions:
                return True
            if verb == "write" and action in write_actions:
                return True
            if verb == "*":
                return True

    return False
