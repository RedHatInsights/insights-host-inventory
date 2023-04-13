from typing import List

from sqlalchemy.orm.scoping import scoped_session

from api.host_query import staleness_timestamps
from app.auth import get_current_identity
from app.exceptions import InventoryException
from app.instrumentation import get_control_rule
from app.instrumentation import log_group_delete_failed
from app.instrumentation import log_group_delete_succeeded
from app.instrumentation import log_host_group_add_failed
from app.instrumentation import log_host_group_add_succeeded
from app.instrumentation import log_host_group_delete_failed
from app.instrumentation import log_host_group_delete_succeeded
from app.logging import get_logger
from app.models import db
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.queue.event_producer import EventProducer
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from app.queue.queue import EGRESS_HOST_FIELDS
from app.serialization import serialize_group
from app.serialization import serialize_host
from lib.db import session_guard
from lib.host_delete import _deleted_by_this_query
from lib.host_repository import find_existing_host_by_id
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.metrics import delete_group_count
from lib.metrics import delete_group_processing_time
from lib.metrics import delete_host_group_count
from lib.metrics import delete_host_group_processing_time


logger = get_logger(__name__)


def _produce_host_update_events(event_producer, host_id_list, group_id_list=[]):
    serialized_groups = [serialize_group(get_group_by_id_from_db(group_id)) for group_id in group_id_list]
    host_list = get_host_list_by_id_list_from_db(host_id_list)

    # Update groups data on each host record
    Host.query.filter(Host.id.in_(host_id_list)).update({"groups": serialized_groups}, synchronize_session="fetch")

    # Send messages
    for host in host_list:
        host.groups = serialized_groups
        serialized_host = serialize_host(host, staleness_timestamps(), EGRESS_HOST_FIELDS)
        headers = message_headers(EventType.updated, serialized_host["insights_id"])
        event = build_event(EventType.updated, serialized_host)
        event_producer.write_event(event, serialized_host["id"], headers, wait=True)


def add_hosts_to_group(group_id: str, host_id_list: List[str], event_producer: EventProducer):
    current_org_id = get_current_identity().org_id

    # Check if the hosts exist in Inventory and have correct org_id
    host_query = Host.query.filter((Host.org_id == current_org_id) & Host.id.in_(host_id_list)).all()
    found_ids_set = {str(host.id) for host in host_query}
    if found_ids_set != set(host_id_list):
        nonexistent_hosts = set(host_id_list) - found_ids_set
        log_host_group_add_failed(logger, host_id_list, group_id)
        raise InventoryException(
            title="Invalid request", detail=f"Could not find existing host(s) with ID {nonexistent_hosts}."
        )

    # Check if the hosts are already associated with another group
    assoc_query = HostGroupAssoc.query.filter(HostGroupAssoc.host_id.in_(host_id_list)).all()
    if assoc_query:
        taken_hosts = [str(assoc.host_id) for assoc in assoc_query]
        log_host_group_add_failed(logger, host_id_list, group_id)
        raise InventoryException(
            title="Invalid request",
            detail=f"The following subset of hosts are already associated with another group: {taken_hosts}.",
        )

    host_group_assoc = [HostGroupAssoc(host_id=host_id, group_id=group_id) for host_id in host_id_list]
    db.session.add_all(host_group_assoc)
    db.session.flush()

    # Produce kafka messages updating the "groups" field for each host
    _produce_host_update_events(event_producer, host_id_list, [group_id])
    log_host_group_add_succeeded(logger, host_id_list, group_id)


def add_group(group_data, event_producer) -> Group:
    logger.debug("Creating a new group: %s", group_data)
    group_name = group_data.get("name")
    org_id = get_current_identity().org_id
    account = get_current_identity().account_number

    with session_guard(db.session):
        new_group = Group(name=group_name, org_id=org_id, account=account)
        db.session.add(new_group)
        db.session.flush()

        host_id_list = group_data.get("host_ids")

        # Add hosts to group
        if host_id_list:
            # gets the ID of the group inside the session
            created_group = Group.query.filter((Group.name == group_name) & (Group.org_id == org_id)).one_or_none()
            add_hosts_to_group(created_group.id, host_id_list, event_producer)

    # gets the ID of the group after it has been committed
    created_group = Group.query.filter((Group.name == group_name) & (Group.org_id == org_id)).one_or_none()

    return created_group


def _remove_all_hosts_from_group(event_producer: EventProducer, group: Group):
    host_ids_to_delete = db.session.query(HostGroupAssoc.host_id).filter(HostGroupAssoc.group_id == group.id).all()
    remove_hosts_from_group(group.id, host_ids_to_delete, event_producer)


def _delete_host_group_assoc(session, event_producer, assoc):
    delete_query = session.query(HostGroupAssoc).filter(
        HostGroupAssoc.group_id == assoc.group_id, HostGroupAssoc.host_id == assoc.host_id
    )
    delete_query.delete(synchronize_session="fetch")
    assoc_deleted = _deleted_by_this_query(assoc)

    _produce_host_update_events(event_producer, [assoc.host_id], [])

    return assoc_deleted


def _delete_group(event_producer: EventProducer, group: Group) -> bool:
    # First, remove all hosts from the requested group.
    group_id = group.id
    _remove_all_hosts_from_group(event_producer, group)

    delete_query = db.session.query(Group).filter(Group.id == group_id)
    delete_query.delete(synchronize_session="fetch")
    return _deleted_by_this_query(group)


def delete_group_list(group_id_list: List[str], event_producer: EventProducer) -> int:
    deletion_count = 0

    with session_guard(db.session):
        for group in (
            db.session.query(Group)
            .filter(Group.org_id == get_current_identity().org_id, Group.id.in_(group_id_list))
            .all()
        ):
            group_id = group.id
            with delete_group_processing_time.time():
                if _delete_group(event_producer, group):
                    deletion_count += 1
                    delete_group_count.inc()
                    log_group_delete_succeeded(logger, group_id, get_control_rule())
                else:
                    log_group_delete_failed(logger, group_id, get_control_rule())

    return deletion_count


def remove_hosts_from_group(group_id, host_id_list, event_producer):
    deletion_count = 0
    group_query = Group.query.filter(Group.org_id == get_current_identity().org_id, Group.id == group_id)

    # First, find the group to make sure the org_id matches
    found_group = group_query.one_or_none()
    if not found_group:
        return 0

    host_group_query = HostGroupAssoc.query.filter(
        HostGroupAssoc.group_id == found_group.id, HostGroupAssoc.host_id.in_(host_id_list)
    )
    with delete_host_group_processing_time.time():
        for assoc in host_group_query.all():
            if _delete_host_group_assoc(db.session, event_producer, assoc):
                deletion_count += 1
                delete_host_group_count.inc()
                log_host_group_delete_succeeded(logger, assoc.host_id, assoc.group_id, get_control_rule())
            else:
                log_host_group_delete_failed(logger, assoc.host_id, assoc.group_id, get_control_rule())

    return deletion_count


def get_group_by_id_from_db(group_id: str) -> Group:
    current_identity = get_current_identity()
    query = Group.query.filter(Group.org_id == current_identity.org_id, Group.id == group_id)
    return query.one_or_none()


def db_create_host_group_assoc(host_id: str, group_id: str) -> HostGroupAssoc:
    if HostGroupAssoc.query.filter(HostGroupAssoc.host_id == host_id).one_or_none():
        raise InventoryException(
            title="Invalid request", detail=f"Host with ID {host_id} is already associated with another group."
        )
    host_group = HostGroupAssoc(host_id=host_id, group_id=group_id)
    db.session.add(host_group)
    return host_group


def db_get_assoc_for_group(group_id: str) -> List[HostGroupAssoc]:
    return HostGroupAssoc.query.filter(HostGroupAssoc.group_id == group_id).all()


def replace_host_list_for_group(
    session: scoped_session, group: Group, host_id_list: List[str], event_producer: EventProducer
) -> List[HostGroupAssoc]:
    group_id = group.id
    with session_guard(session):
        _remove_all_hosts_from_group(event_producer, group)
        assoc_list = []
        for host_id in host_id_list:
            if not find_existing_host_by_id(get_current_identity(), host_id):
                raise InventoryException(title="Invalid request", detail=f"Host with ID {host_id} does not exist.")

            assoc_list.append(db_create_host_group_assoc(host_id, group_id))
            # Update modified_on timestamp on the group
            group.update_modified_on()

    _produce_host_update_events(event_producer, host_id_list, [group_id])
    return assoc_list


def patch_group(group: Group, patch_data: dict, event_producer: EventProducer):
    group_id = group.id
    new_host_ids = patch_data.get("host_ids")

    # Set new group name if provided
    if group.patch(patch_data) and new_host_ids is None:
        # If anything was updated, and the host list is not being replaced,
        # send update messages to existing hosts. Otherwise, wait until the host list is replaced
        # so we don't produce messages that will be instantly obsoleted.
        existing_host_ids = db.session.query(HostGroupAssoc.host_id).filter(HostGroupAssoc.group_id == group_id).all()
        if new_host_ids is None:
            _produce_host_update_events(event_producer, existing_host_ids, [group_id])

    # Next, replace the host-group associations and produce update messages
    if new_host_ids is not None:
        replace_host_list_for_group(db.session, group, new_host_ids, event_producer)
