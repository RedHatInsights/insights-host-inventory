from app.logging import get_logger
from app.logging import threadctx

import json

logger = get_logger(__name__)


def get_rbac_permissions():
    with open("utils/rbac-mock-data/inv-read-only.json", "r") as rbac_response:
        resp_data = json.load(rbac_response)
        return resp_data["data"]

def check_rbac_permissions():
    threadctx.host_read_permission = False
    threadctx.host_write_permission = False

    rbac_data = get_rbac_permissions()

    for rbac_permission in rbac_data:
        _, resource, verb = rbac_permission["permission"].split(":")

        if resource == "hosts" or resource == "*":
            if verb == "read":
                threadctx.host_read_permission = True
            if verb == "write":
                threadctx.host_write_permission = True
            if verb == "*":
                threadctx.host_read_permission = True
                threadctx.host_write_permission = True

    logger.info('RBAC Hosts Write %s', threadctx.host_write_permission)
    logger.info('RBAC Hosts Read %s', threadctx.host_read_permission)
    logger.info('Fetched RBAC Permissions %s', rbac_data)
