import flask
from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from api import api_operation
from api import flask_json_response
from api import metrics
from api.group_query import build_group_response
from app import db
from app import inventory_config
from app import Permission
from app.exceptions import InventoryException
from app.instrumentation import get_control_rule
from app.instrumentation import log_add_group_failed
from app.instrumentation import log_add_group_succeeded
from app.instrumentation import log_patch_group_failed
from app.instrumentation import log_patch_group_success
from app.logging import get_logger
from app.models import GroupSchema
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.group_repository import add_group
from lib.group_repository import add_hosts_to_group
from lib.group_repository import delete_group_list
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import remove_hosts_from_group
from lib.group_repository import replace_host_list_for_group
from lib.metrics import create_group_count
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


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def create_group(body):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return flask.Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        validated_create_group_data = GroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while creating group: {body}")
        return (
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "title": "Validation Error",
                "detail": str(e.messages),
                "type": "unknown",
            },
            status.HTTP_400_BAD_REQUEST,
        )

    try:
        created_group = add_group(validated_create_group_data)
        log_add_group_succeeded(logger, created_group.id, get_control_rule())
        create_group_count.inc()
    except IntegrityError:
        log_add_group_failed(logger, validated_create_group_data.get("name"), get_control_rule())
        logger.exception(f"A group with details {validated_create_group_data} already exists.")
        return (
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "title": "Integrity error",
                "detail": f"A group with details {validated_create_group_data} already exists.",
                "type": "unknown",
            },
            status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        log_add_group_failed(logger, validated_create_group_data.get("name"), get_control_rule())
        logger.exception(f"Error adding group with details {validated_create_group_data}")
        return (
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "title": f"Error adding group with details {validated_create_group_data}",
                "detail": str(e.messages),
                "type": "unknown",
            },
            status.HTTP_400_BAD_REQUEST,
        )

    host_id_list = validated_create_group_data.get("host_ids")

    if host_id_list:
        add_hosts_to_group(created_group, host_id_list)

    return flask_json_response(build_group_response(created_group), status.HTTP_201_CREATED)


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def patch_group_by_id(group_id, body):
    try:
        validated_patch_group_data = GroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while patching group: {group_id} - {body}")
        return ({"status": 400, "title": "Bad Request", "detail": str(e.messages), "type": "unknown"}, 400)

    # First, get the group and update it
    group_to_update = get_group_by_id_from_db(group_id)

    if not group_to_update:
        log_patch_group_failed(logger, group_id)
        flask.abort(status.HTTP_404_NOT_FOUND)

    # Separate out the host IDs because they're not stored on the Group
    group_to_update.patch(validated_patch_group_data)
    host_id_list = validated_patch_group_data.get("host_ids")

    # Next, replace the host-group associations
    assoc_list = []
    if host_id_list is not None:
        try:
            assoc_list = replace_host_list_for_group(db.session, group_to_update, host_id_list)
        except InventoryException as ie:
            log_patch_group_failed(logger, group_id)
            flask.abort(status.HTTP_400_BAD_REQUEST, str(ie.detail))

    if db.session.is_modified(group_to_update) or any(db.session.is_modified(assoc) for assoc in assoc_list):
        try:
            db.session.commit()
        except IntegrityError:
            log_patch_group_failed(logger, group_id)
            flask.abort(
                status.HTTP_400_BAD_REQUEST,
                f"Group with name '{validated_patch_group_data.get('name')}' already exists.",
            )

    # TODO: Emit patch event for group, and one per assoc
    updated_group = get_group_by_id_from_db(group_id)
    log_patch_group_success(logger, group_id)
    return flask_json_response(build_group_response(updated_group), status.HTTP_200_OK)


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
