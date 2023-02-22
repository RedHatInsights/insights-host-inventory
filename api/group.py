import flask
from flask_api import status

from api import api_operation
from api import metrics
from app import inventory_config
from app import Permission
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.group_repository import add_group
from lib.group_repository import add_hosts_to_group
from lib.group_repository import delete_group_list
from lib.group_repository import remove_hosts_from_group
from lib.middleware import rbac


def get_group_list(
    group_name=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
):
    pass


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def create_group(body):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return flask.Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    created_group_id = add_group(body)

    if not created_group_id:
        flask.abort(status.HTTP_400_BAD_REQUEST, "Group could not be created.")

    updated_group = add_hosts_to_group(created_group_id, body.get("host_ids"))

    return flask.Response(updated_group, status.HTTP_201_CREATED)


def patch_group_by_id(group_id, group_data):
    pass


def update_group_details(group_id, group_data):
    pass


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def delete_groups(group_id_list):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return flask.Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    delete_count = delete_group_list(group_id_list, inventory_config().host_delete_chunk_size)

    if delete_count == 0:
        flask.abort(status.HTTP_404_NOT_FOUND, "No groups found for deletion.")

    return flask.Response(None, status.HTTP_204_NO_CONTENT)


def get_groups_by_id(group_id_list):
    pass


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def delete_hosts_from_group(group_id, host_id_list):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return flask.Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    delete_count = remove_hosts_from_group(group_id, host_id_list)

    if delete_count == 0:
        flask.abort(status.HTTP_404_NOT_FOUND, "Group or hosts not found.")

    return flask.Response(None, status.HTTP_204_NO_CONTENT)
