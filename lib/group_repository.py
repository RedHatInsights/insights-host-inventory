from typing import Optional
from uuid import UUID

from sqlalchemy import select

from api.cache import delete_cached_system_keys
from api.host_query import staleness_timestamps
from api.staleness_query import get_staleness_obj
from app.auth import get_current_identity
from app.auth.identity import Identity
from app.auth.identity import to_auth_header
from app.exceptions import InventoryException
from app.instrumentation import get_control_rule
from app.instrumentation import log_get_group_list_failed
from app.instrumentation import log_group_delete_failed
from app.instrumentation import log_group_delete_succeeded
from app.instrumentation import log_host_group_add_failed
from app.instrumentation import log_host_group_add_succeeded
from app.instrumentation import log_host_group_delete_failed
from app.instrumentation import log_host_group_delete_succeeded
from app.logging import get_logger
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import db
from app.models import deleted_by_this_query
from app.queue.event_producer import EventProducer
from app.queue.events import EventType
from app.queue.events import build_event
from app.queue.events import message_headers
from app.serialization import serialize_group
from app.serialization import serialize_host
from app.staleness_serialization import AttrDict
from lib.db import session_guard
from lib.feature_flags import FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION
from lib.feature_flags import get_flag_value
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.metrics import delete_group_count
from lib.metrics import delete_group_processing_time
from lib.metrics import delete_host_group_count
from lib.metrics import delete_host_group_processing_time
from lib.middleware import rbac_create_ungrouped_hosts_workspace

logger = get_logger(__name__)


def _update_hosts_for_group_changes(host_id_list: list[str], group_id_list: list[str], identity: Identity):
    if group_id_list is None:
        group_id_list = []

    serialized_groups = [
        serialize_group(get_group_by_id_from_db(group_id, identity.org_id), identity.org_id)
        for group_id in group_id_list
    ]

    # Update groups data on each host record
    Host.query.filter(Host.id.in_(host_id_list)).update({"groups": serialized_groups}, synchronize_session="fetch")
    db.session.commit()
    host_list = get_host_list_by_id_list_from_db(host_id_list, identity)
    return serialized_groups, host_list


def _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=None):
    metadata = {"b64_identity": to_auth_header(identity)}  # Note: This should be moved to an API file

    # Send messages
    for host in host_list:
        host.groups = serialized_groups
        serialized_host = serialize_host(host, staleness_timestamps(), staleness=staleness)
        headers = message_headers(
            EventType.updated,
            host.canonical_facts.get("insights_id"),
            host.reporter,
            host.system_profile_facts.get("host_type"),
            host.system_profile_facts.get("operating_system", {}).get("name"),
            str(host.system_profile_facts.get("bootc_status", {}).get("booted") is not None),
        )
        event = build_event(EventType.updated, serialized_host, platform_metadata=metadata)
        event_producer.write_event(event, serialized_host["id"], headers, wait=True)


def _invalidate_system_cache(host_list: list[Host], identity: Identity):
    for host in host_list:
        insights_id = host.canonical_facts.get("insights_id")
        owner_id = host.system_profile_facts.get("owner_id")
        if insights_id and owner_id:
            delete_cached_system_keys(insights_id=insights_id, org_id=identity.org_id, owner_id=owner_id)


def _add_hosts_to_group(group_id: str, host_id_list: list[str], org_id: str):
    # Check if the hosts exist in Inventory and have correct org_id
    host_query = Host.query.filter((Host.org_id == org_id) & Host.id.in_(host_id_list)).all()
    found_ids_set = {str(host.id) for host in host_query}
    if found_ids_set != set(host_id_list):
        nonexistent_hosts = set(host_id_list) - found_ids_set
        log_host_group_add_failed(logger, host_id_list, group_id)
        raise InventoryException(
            title="Invalid request", detail=f"Could not find existing host(s) with ID {nonexistent_hosts}."
        )

    # Check if the hosts are already associated with another group
    assoc_query = HostGroupAssoc.query.filter(
        HostGroupAssoc.host_id.in_(host_id_list), HostGroupAssoc.group_id != group_id
    ).all()
    if assoc_query:
        taken_hosts = [str(assoc.host_id) for assoc in assoc_query]
        log_host_group_add_failed(logger, host_id_list, group_id)
        raise InventoryException(
            title="Invalid request",
            detail=f"The following subset of hosts are already associated with another group: {taken_hosts}.",
        )

    # Fitler out hosts that are already in the group
    assoc_query = HostGroupAssoc.query.filter(
        HostGroupAssoc.host_id.in_(host_id_list), HostGroupAssoc.group_id == group_id
    ).all()
    ids_already_in_this_group = [str(assoc.host_id) for assoc in assoc_query]

    host_group_assoc = [
        HostGroupAssoc(host_id=host_id, group_id=group_id)
        for host_id in host_id_list
        if host_id not in ids_already_in_this_group
    ]
    db.session.add_all(host_group_assoc)

    _update_group_update_time(group_id, org_id)

    log_host_group_add_succeeded(logger, host_id_list, group_id)


def add_hosts_to_group(group_id: str, host_id_list: list[str], identity: Identity, event_producer: EventProducer):
    staleness = get_staleness_obj(identity.org_id)
    with session_guard(db.session):
        _add_hosts_to_group(group_id, host_id_list, identity.org_id)

    # Produce update messages once the DB session has been closed
    serialized_groups, host_list = _update_hosts_for_group_changes(
        host_id_list, group_id_list=[group_id], identity=identity
    )
    _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=staleness)
    _invalidate_system_cache(host_list, identity)


def add_group(
    group_name: Optional[str],
    org_id: str,
    account: Optional[str] = None,
    group_id: Optional[UUID] = None,
    ungrouped: bool = False,
) -> Group:
    new_group = Group(org_id=org_id, name=group_name, account=account, id=group_id, ungrouped=ungrouped)
    db.session.add(new_group)
    db.session.flush()

    # gets the ID of the group after it has been committed
    created_group = Group.query.filter((Group.name == group_name) & (Group.org_id == org_id)).one_or_none()
    return created_group


def add_group_with_hosts(
    group_name: Optional[str],
    host_id_list: list[str],
    identity: Identity,
    account: str,
    group_id: Optional[UUID],
    ungrouped: bool,
    staleness: AttrDict,
    event_producer: EventProducer,
) -> Group:
    with session_guard(db.session):
        # Create group
        created_group = add_group(group_name, identity.org_id, account, group_id, ungrouped)

        # Add hosts to group
        if host_id_list:
            _add_hosts_to_group(created_group.id, host_id_list, identity.org_id)

    # gets the ID of the group after it has been committed
    created_group = Group.query.filter((Group.name == group_name) & (Group.org_id == identity.org_id)).one_or_none()

    # Produce update messages once the DB session has been closed
    serialized_groups, host_list = _update_hosts_for_group_changes(
        host_id_list, group_id_list=[created_group.id], identity=identity
    )
    _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=staleness)
    _invalidate_system_cache(host_list, identity)

    return created_group


def create_group_from_payload(group_data: dict, event_producer: EventProducer, group_id: UUID) -> Group:
    logger.debug("Creating a new group: %s", group_data)
    identity = get_current_identity()
    return add_group_with_hosts(
        group_data.get("name"),
        group_data.get("host_ids", []),
        identity=identity,
        account=identity.account_number,
        group_id=group_id,
        ungrouped=False,
        staleness=get_staleness_obj(identity.org_id),
        event_producer=event_producer,
    )


def _remove_all_hosts_from_group(group: Group):
    host_group_assocs_to_delete = HostGroupAssoc.query.filter(HostGroupAssoc.group_id == group.id).all()
    _remove_hosts_from_group(group.id, [assoc.host_id for assoc in host_group_assocs_to_delete])


def _delete_host_group_assoc(session, assoc):
    delete_query = session.query(HostGroupAssoc).filter(
        HostGroupAssoc.group_id == assoc.group_id, HostGroupAssoc.host_id == assoc.host_id
    )
    delete_query.delete(synchronize_session="fetch")
    assoc_deleted = deleted_by_this_query(assoc)

    return assoc_deleted


def _delete_group(group: Group) -> bool:
    # First, remove all hosts from the requested group.
    group_id = group.id
    _remove_all_hosts_from_group(group)

    delete_query = db.session.query(Group).filter(Group.id == group_id)
    delete_query.delete(synchronize_session="fetch")
    return deleted_by_this_query(group)


def delete_group_list(group_id_list: list[str], identity: Identity, event_producer: EventProducer) -> int:
    deletion_count = 0
    deleted_host_ids = []
    staleness = get_staleness_obj(identity.org_id)
    with session_guard(db.session):
        query = (
            select(HostGroupAssoc)
            .join(Group, HostGroupAssoc.group_id == Group.id)
            .filter(Group.org_id == identity.org_id, HostGroupAssoc.group_id.in_(group_id_list))
        )

        assocs_to_delete = db.session.execute(query).scalars().all()

        deleted_host_ids = [assoc.host_id for assoc in assocs_to_delete]

        for group in (
            db.session.query(Group).filter(Group.org_id == identity.org_id, Group.id.in_(group_id_list)).all()
        ):
            group_id = group.id

            with delete_group_processing_time.time():
                if _delete_group(group):
                    deletion_count += 1
                    delete_group_count.inc()
                    log_group_delete_succeeded(logger, group_id, get_control_rule())
                else:
                    log_group_delete_failed(logger, group_id, get_control_rule())

    serialized_groups, host_list = _update_hosts_for_group_changes(deleted_host_ids, [], identity)
    _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=staleness)
    _invalidate_system_cache(host_list, identity)
    return deletion_count


def remove_hosts_from_group(group_id, host_id_list, identity, event_producer):
    removed_host_ids = []
    staleness = get_staleness_obj(identity.org_id)
    with session_guard(db.session):
        removed_host_ids = _remove_hosts_from_group(group_id, host_id_list)
        if get_flag_value(FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION):
            # Add hosts to the "ungrouped" group
            ungrouped_group = get_or_create_ungrouped_hosts_group_for_identity(identity)
            _add_hosts_to_group(str(ungrouped_group.id), removed_host_ids, identity.org_id)

    serialized_groups, host_list = _update_hosts_for_group_changes(removed_host_ids, [], identity)
    _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=staleness)
    _invalidate_system_cache(host_list, identity)
    return len(removed_host_ids)


def _remove_hosts_from_group(group_id, host_id_list):
    removed_host_ids = []
    org_id = get_current_identity().org_id
    group_query = Group.query.filter(Group.org_id == org_id, Group.id == group_id)

    # First, find the group to make sure the org_id matches
    found_group = group_query.one_or_none()
    if not found_group:
        log_get_group_list_failed(logger)
        return []

    host_group_query = HostGroupAssoc.query.filter(
        HostGroupAssoc.group_id == found_group.id, HostGroupAssoc.host_id.in_(host_id_list)
    )
    with delete_host_group_processing_time.time():
        for assoc in host_group_query.all():
            if _delete_host_group_assoc(db.session, assoc):
                removed_host_ids.append(assoc.host_id)
                delete_host_group_count.inc()
                log_host_group_delete_succeeded(logger, assoc.host_id, assoc.group_id, get_control_rule())
            else:
                log_host_group_delete_failed(logger, assoc.host_id, assoc.group_id, get_control_rule())

    _update_group_update_time(group_id, org_id)

    return removed_host_ids


def get_group_by_id_from_db(group_id: str, org_id: str) -> Group:
    query = Group.query.filter(Group.org_id == org_id, Group.id == group_id)
    return query.one_or_none()


def patch_group(group: Group, patch_data: dict, event_producer: EventProducer):
    group_id = group.id
    host_id_data = patch_data.get("host_ids")
    new_host_ids = {host_id for host_id in host_id_data} if host_id_data is not None else None

    existing_host_uuids = db.session.query(HostGroupAssoc.host_id).filter(HostGroupAssoc.group_id == group_id).all()
    existing_host_ids = {str(host_id[0]) for host_id in existing_host_uuids}
    identity = get_current_identity()
    staleness = get_staleness_obj(identity.org_id)

    with session_guard(db.session):
        # Patch Group data, if provided
        group_patched = group.patch(patch_data)

        # Update host list, if provided
        if new_host_ids is not None:
            _remove_hosts_from_group(group_id, list(existing_host_ids - new_host_ids))
            _add_hosts_to_group(group_id, list(new_host_ids - existing_host_ids), identity.org_id)
            if get_flag_value(FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION):
                # Add hosts to the "ungrouped" group
                ungrouped_group = get_or_create_ungrouped_hosts_group_for_identity(identity)
                _add_hosts_to_group(str(ungrouped_group.id), list(existing_host_ids - new_host_ids), identity.org_id)

    # Send MQ messages
    if group_patched and host_id_data is None:
        # If anything was updated, and the host list is not being replaced,
        # send update messages to existing hosts. Otherwise, wait until the host list is replaced
        # so we don't produce messages that will be instantly obsoleted.
        serialized_groups, host_list = _update_hosts_for_group_changes(list(existing_host_ids), [group_id], identity)
        _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=staleness)
        _invalidate_system_cache(host_list, identity)
    elif new_host_ids is not None:
        # If host IDs were provided, we need to update the host list.
        # First, update the modified date for the group
        group.update_modified_on()
        db.session.add(group)

        deleted_host_uuids = [str(host_id) for host_id in (existing_host_ids - new_host_ids)]
        serialized_groups, host_list = _update_hosts_for_group_changes(deleted_host_uuids, [], identity)
        _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=staleness)
        _invalidate_system_cache(host_list, identity)

        added_host_uuids = [str(host_id) for host_id in new_host_ids]
        serialized_groups, host_list = _update_hosts_for_group_changes(added_host_uuids, [group_id], identity)
        _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=staleness)
        _invalidate_system_cache(host_list, identity)


def _update_group_update_time(group_id: str, org_id: str):
    group = get_group_by_id_from_db(group_id, org_id)
    group.update_modified_on()
    db.session.add(group)
    db.session.flush()


def get_group_using_host_id(host_id: str, org_id: str):
    assoc = HostGroupAssoc.query.filter(HostGroupAssoc.host_id == host_id).one_or_none()
    if assoc:
        # check current identity against db
        return get_group_by_id_from_db(str(assoc.group_id), org_id)
    else:
        return None


def get_or_create_ungrouped_hosts_group_for_identity(identity: Identity) -> Group:
    group = Group.query.filter(Group.org_id == identity.org_id, Group.ungrouped.is_(True)).one_or_none()

    # If the "ungrouped" Group exists, return it.
    if group is not None:
        return group

    # Otherwise, create the workspace
    workspace_id = rbac_create_ungrouped_hosts_workspace()

    # Create "ungrouped" group for this org using group ID == workspace ID
    return add_group(
        group_name="ungrouped",
        org_id=identity.org_id,
        account=identity.account_number,
        group_id=workspace_id,
        ungrouped=True,
    )
