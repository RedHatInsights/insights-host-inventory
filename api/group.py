import flask
from flask_api import status
from marshmallow import ValidationError

from api import api_operation
from api import flask_json_response
from api import metrics
from api.group_query import build_group_response
from app import db
from app import inventory_config
from app import Permission
from app.instrumentation import log_patch_group_failed
from app.instrumentation import log_patch_group_success
from app.logging import get_logger
from app.models import PatchGroupSchema
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.group_repository import delete_group_list
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import remove_hosts_from_group
from lib.group_repository import replace_host_list_for_group
from lib.middleware import rbac


logger = get_logger(__name__)


def get_group_list(
    group_name=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
):
    pass


def create_group(group_data):
    pass


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def patch_group_by_id(group_id, body):
    try:
        validated_patch_group_data = PatchGroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while patching group: {group_id} - {body}")
        return ({"status": 400, "title": "Bad Request", "detail": str(e.messages), "type": "unknown"}, 400)

    # First, get the group and update it
    group_to_update = get_group_by_id_from_db(group_id)

    if not group_to_update:
        log_patch_group_failed(logger, group_id)
        return flask.abort(status.HTTP_404_NOT_FOUND)

    # Separate out the host IDs because they're not stored on the Group
    host_id_list = validated_patch_group_data.pop("host_ids", None)
    group_to_update.patch(validated_patch_group_data)

    # Next, replace the host-group associations
    assoc_list = []
    if host_id_list is not None:
        assoc_list = replace_host_list_for_group(db.session, group_to_update, host_id_list)

    if db.session.is_modified(group_to_update) or any(db.session.is_modified(assoc) for assoc in assoc_list):
        db.session.commit()
        # TODO: Emit patch event for group, and one per assoc

    updated_group = get_group_by_id_from_db(group_id)
    log_patch_group_success(logger, group_id)
    return flask_json_response(build_group_response(updated_group), status.HTTP_200_OK)


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
