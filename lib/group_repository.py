import time
from uuid import UUID

from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.serialization import serialize_group_with_host_count
from app.serialization import serialize_host
from app.staleness_serialization import AttrDict
from lib.db import session_guard
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.host_repository import get_non_culled_hosts_count_in_group
from lib.host_repository import host_query
from lib.metrics import delete_group_count
from lib.metrics import delete_group_processing_time
from lib.metrics import delete_host_group_count
from lib.metrics import delete_host_group_processing_time
from lib.middleware import rbac_create_ungrouped_hosts_workspace

logger = get_logger(__name__)


def _update_hosts_for_group_changes(host_id_list: list[str], group_id_list: list[str], identity: Identity):
    if not host_id_list:
        return [], []

    if group_id_list is None:
        group_id_list = []

    serialized_groups = [
        serialize_group(get_group_by_id_from_db(group_id, identity.org_id)) for group_id in group_id_list
    ]

    # Update groups data on each host record
    # Use ORM update (not bulk update) to trigger event listeners
    # The _has_outbox_relevant_changes function will determine if outbox event is needed
    # (only when group IDs change, not just names)
    hosts = db.session.query(Host).filter(Host.id.in_(host_id_list), Host.org_id == identity.org_id).all()
    for host in hosts:
        host.groups = serialized_groups

    # Flush to ensure outbox events are tracked before commit
    db.session.flush()

    return serialized_groups, host_id_list


def _produce_host_update_events(event_producer, serialized_groups, host_list, identity, staleness=None):
    metadata = {"b64_identity": to_auth_header(identity)}  # Note: This should be moved to an API file

    # Send messages
    for host in host_list:
        host.groups = serialized_groups
        serialized_host = serialize_host(host, staleness_timestamps(), staleness=staleness)
        headers = message_headers(
            EventType.updated,
            str(host.insights_id),
            host.reporter,
            host.system_profile_facts.get("host_type"),
            host.system_profile_facts.get("operating_system", {}).get("name"),
            str(host.system_profile_facts.get("bootc_status", {}).get("booted") is not None),
        )
        event = build_event(EventType.updated, serialized_host, platform_metadata=metadata)
        event_producer.write_event(event, serialized_host["id"], headers, wait=True)


def _invalidate_system_cache(host_list: list[Host], identity: Identity):
    for host in host_list:
        insights_id = host.insights_id
        owner_id = host.system_profile_facts.get("owner_id")
        if insights_id and owner_id:
            delete_cached_system_keys(insights_id=str(insights_id), org_id=identity.org_id, owner_id=owner_id)


def validate_add_host_list_to_group_for_group_create(host_id_list: list[str], group_name: str, org_id: str):
    # Check if the hosts exist in Inventory and have correct org_id
    query = host_query(org_id).filter(Host.id.in_(host_id_list)).all()
    found_ids_set = {str(host.id) for host in query}
    if found_ids_set != set(host_id_list):
        nonexistent_hosts = set(host_id_list) - found_ids_set
        log_host_group_add_failed(logger, host_id_list, group_name)
        raise InventoryException(
            title="Invalid request", detail=f"Could not find existing host(s) with ID {nonexistent_hosts}."
        )

    # Check if the hosts are already associated with another (ungrouped) group
    if assoc_query := (
        HostGroupAssoc.query.join(Group)
        .filter(HostGroupAssoc.host_id.in_(host_id_list), Group.ungrouped.is_(False))
        .all()
    ):
        taken_hosts = [str(assoc.host_id) for assoc in assoc_query]
        log_host_group_add_failed(logger, host_id_list, group_name)
        raise InventoryException(
            title="Invalid request",
            detail=f"The following subset of hosts are already associated with another group: {taken_hosts}.",
        )


def validate_add_host_list_to_group(host_id_list: list[str], group_id: str, org_id: str):
    # Check if the hosts exist in Inventory and have correct org_id
    host_query = db.session.query(Host).filter((Host.org_id == org_id) & Host.id.in_(host_id_list)).all()
    found_ids_set = {str(host.id) for host in host_query}
    if found_ids_set != set(host_id_list):
        nonexistent_hosts = set(host_id_list) - found_ids_set
        log_host_group_add_failed(logger, host_id_list, group_id)
        raise InventoryException(
            title="Invalid request", detail=f"Could not find existing host(s) with ID {nonexistent_hosts}."
        )

    # Check if the hosts are already associated with another (ungrouped) group
    if assoc_query := (
        db.session.query(HostGroupAssoc)
        .join(Group)
        .filter(
            HostGroupAssoc.host_id.in_(host_id_list), HostGroupAssoc.group_id != group_id, Group.ungrouped.is_(False)
        )
        .all()
    ):
        taken_hosts = [str(assoc.host_id) for assoc in assoc_query]
        log_host_group_add_failed(logger, host_id_list, group_id)
        raise InventoryException(
            title="Invalid request",
            detail=f"The following subset of hosts are already associated with another group: {taken_hosts}.",
        )


def _add_hosts_to_group(group_id: str, host_id_list: list[str], org_id: str):
    # Validate that the hosts exist and can be added to the group
    # This must happen BEFORE any database modifications to ensure clean rollback on failure
    validate_add_host_list_to_group(host_id_list, group_id, org_id)

    # Filter out hosts that are already in the group
    assoc_query = HostGroupAssoc.query.filter(
        HostGroupAssoc.host_id.in_(host_id_list), HostGroupAssoc.group_id == group_id
    ).all()
    ids_already_in_this_group = [str(assoc.host_id) for assoc in assoc_query]

    # Delete any prior host-group associations, which should now just be to "ungrouped" group
    HostGroupAssoc.query.filter(HostGroupAssoc.host_id.in_(host_id_list), HostGroupAssoc.group_id != group_id).delete(
        synchronize_session="fetch"
    )

    host_group_assoc = [
        HostGroupAssoc(host_id=host_id, group_id=group_id, org_id=org_id)
        for host_id in host_id_list
        if host_id not in ids_already_in_this_group
    ]
    db.session.add_all(host_group_assoc)

    _update_group_update_time(group_id, org_id)

    log_host_group_add_succeeded(logger, host_id_list, group_id)


def wait_for_workspace_event(workspace_id: str, event_type: EventType, org_id: str, *, timeout: int = 5):
    conn = db.session.connection().connection
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute(f"LISTEN workspace_{event_type.name};")
    timeout_start = time.time()
    try:
        # It's possible that the MQ message may have already been processed,
        # so we check if the group already exists first.
        logger.debug(f"Checking if workspace {workspace_id} exists in org {org_id}")
        if get_group_by_id_from_db(workspace_id, org_id) is not None:
            logger.debug(f"Workspace {workspace_id} found in org {org_id}")
            return

        logger.debug(f"Waiting for workspace {workspace_id} to be created via MQ event")
        while time.time() < timeout_start + timeout:
            conn.poll()
            for notify in conn.notifies:
                logger.debug(f"Notify received for workspace {notify.payload}")
                if str(notify.payload) == str(workspace_id):
                    return

            conn.notifies.clear()
            time.sleep(0.1)
    finally:
        cursor.execute(f"UNLISTEN workspace_{event_type.name};")
        cursor.close()

    raise TimeoutError("No workspace creation message consumed in time.")


def _process_host_changes(
    host_id_list: list[str],
    serialized_groups: list[str],
    staleness: AttrDict,
    identity: Identity,
    event_producer: EventProducer,
):
    # Refresh hosts to ensure they're bound to the current session
    refreshed_host_list = get_host_list_by_id_list_from_db(host_id_list, identity)

    _produce_host_update_events(event_producer, serialized_groups, refreshed_host_list, identity, staleness=staleness)
    _invalidate_system_cache(refreshed_host_list, identity)


def add_hosts_to_group(
    group_id: str,
    host_id_list: list[str],
    identity: Identity,
    event_producer: EventProducer,
):
    staleness = get_staleness_obj(identity.org_id)
    with session_guard(db.session):
        _add_hosts_to_group(group_id, host_id_list, identity.org_id)
        serialized_groups, host_id_list = _update_hosts_for_group_changes(
            host_id_list, group_id_list=[group_id], identity=identity
        )

    # Session is committed and closed here
    _process_host_changes(host_id_list, serialized_groups, staleness, identity, event_producer)


def add_group(
    group_name: str | None,
    org_id: str,
    account: str | None = None,
    group_id: UUID | None = None,
    ungrouped: bool = False,
    session: Session | None = None,
) -> Group:
    session = session or db.session
    new_group = Group(org_id=org_id, name=group_name, account=account, id=group_id, ungrouped=ungrouped)
    session.add(new_group)
    session.flush()

    # gets the ID of the group after it has been committed
    return new_group


def add_group_with_hosts(
    group_name: str | None,
    host_id_list: list[str],
    identity: Identity,
    account: str,
    group_id: UUID | None,
    ungrouped: bool,
    staleness: AttrDict,
    event_producer: EventProducer,
) -> Group:
    with session_guard(db.session):
        # Create group
        created_group = add_group(group_name, identity.org_id, account, group_id, ungrouped)
        created_group_id = created_group.id

        # Add hosts to group
        if host_id_list:
            _add_hosts_to_group(created_group.id, host_id_list, identity.org_id)

        # gets the ID of the group after it has been committed
        created_group = get_group_by_id_from_db(created_group_id, identity.org_id)

        # Produce update messages once the DB session has been closed
        serialized_groups, host_id_list = _update_hosts_for_group_changes(
            host_id_list, group_id_list=[created_group.id], identity=identity
        )

    _process_host_changes(host_id_list, serialized_groups, staleness, identity, event_producer)

    # Return a fresh group object bound to a new session to avoid DetachedInstanceError
    return get_group_by_id_from_db(created_group_id, identity.org_id)


def create_group_from_payload(group_data: dict, event_producer: EventProducer, group_id: UUID | None) -> Group:
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


def _remove_all_hosts_from_group(group: Group, identity: Identity):
    host_ids = [
        row[0] for row in db.session.query(HostGroupAssoc.host_id).filter(HostGroupAssoc.group_id == group.id).all()
    ]
    _remove_hosts_from_group(group.id, host_ids, identity.org_id)
    # If Kessel flag is on, assign hosts to "ungrouped" group
    ungrouped_id = get_or_create_ungrouped_hosts_group_for_identity(identity).id
    _add_hosts_to_group(ungrouped_id, [str(host_id) for host_id in host_ids], identity.org_id)


def _delete_host_group_assoc(session, assoc):
    delete_query = session.query(HostGroupAssoc).filter(
        HostGroupAssoc.group_id == assoc.group_id, HostGroupAssoc.host_id == assoc.host_id
    )
    delete_query.delete(synchronize_session="fetch")
    assoc_deleted = deleted_by_this_query(assoc)

    return assoc_deleted


def _delete_group(group: Group, identity: Identity) -> bool:
    # First, remove all hosts from the requested group.
    group_id = group.id
    _remove_all_hosts_from_group(group, identity)

    delete_query = db.session.query(Group).filter(Group.id == group_id)
    delete_query.delete(synchronize_session="fetch")
    return deleted_by_this_query(group)


def delete_group_list(group_id_list: list[str], identity: Identity, event_producer: EventProducer) -> int:
    deletion_count = 0
    deleted_host_ids = []

    host_id_list = []
    with session_guard(db.session):
        staleness = get_staleness_obj(identity.org_id)
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
                if _delete_group(group, identity):
                    deletion_count += 1
                    delete_group_count.inc()
                    log_group_delete_succeeded(logger, group_id, get_control_rule())
                else:
                    log_group_delete_failed(logger, group_id, get_control_rule())

        new_group_list = (
            [str(get_or_create_ungrouped_hosts_group_for_identity(identity).id)] if deleted_host_ids else []
        )

        serialized_groups, host_id_list = _update_hosts_for_group_changes(deleted_host_ids, new_group_list, identity)

    # session_guard commits and closes the session above this line
    _process_host_changes(host_id_list, serialized_groups, staleness, identity, event_producer)
    return deletion_count


def remove_hosts_from_group(group_id, host_id_list, identity, event_producer):
    removed_host_ids = []
    staleness = get_staleness_obj(identity.org_id)
    group_id_list = []
    serialized_groups = []

    with session_guard(db.session):
        removed_host_ids = _remove_hosts_from_group(group_id, host_id_list, identity.org_id)
        # Add hosts to the "ungrouped" group
        ungrouped_group_id = str(get_or_create_ungrouped_hosts_group_for_identity(identity).id)
        _add_hosts_to_group(ungrouped_group_id, [str(host_id) for host_id in removed_host_ids], identity.org_id)
        group_id_list = [ungrouped_group_id]

        serialized_groups, host_id_list = _update_hosts_for_group_changes(removed_host_ids, group_id_list, identity)

    _process_host_changes(host_id_list, serialized_groups, staleness, identity, event_producer)

    return len(removed_host_ids)


def _remove_hosts_from_group(group_id, host_id_list, org_id):
    removed_host_ids = []
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


def get_group_by_id_from_db(group_id: str, org_id: str, session: Session | None = None) -> Group:
    session = session or db.session
    query = session.query(Group).filter(Group.org_id == org_id, Group.id == group_id)
    return query.one_or_none()


def get_groups_by_id_list_from_db(
    group_id_list: list[str], org_id: str, session: Session | None = None
) -> list[Group]:
    session = session or db.session
    return session.query(Group).filter(Group.org_id == org_id, Group.id.in_(group_id_list)).all()


def patch_group(group: Group, patch_data: dict, identity: Identity, event_producer: EventProducer):
    group_id = group.id
    host_id_data = patch_data.get("host_ids")
    new_host_ids = set(host_id_data) if host_id_data is not None else None
    removed_group_id_list = []

    existing_host_uuids = db.session.query(HostGroupAssoc.host_id).filter(HostGroupAssoc.group_id == group_id).all()
    existing_host_ids = {str(host_id[0]) for host_id in existing_host_uuids}
    staleness = get_staleness_obj(identity.org_id)

    serialized_groups = []

    # Variables to store results for event production after session commit
    removed_serialized_groups = None
    added_serialized_groups = None

    with session_guard(db.session):
        # Patch Group data, if provided
        group_patched = group.patch(patch_data)

        # Update host list, if provided
        if new_host_ids is not None:
            hosts_to_add = list(new_host_ids - existing_host_ids)
            if hosts_to_add:  # Only validate if there are new hosts to add
                validate_add_host_list_to_group(hosts_to_add, group_id, identity.org_id)

            _add_hosts_to_group(group_id, hosts_to_add, identity.org_id)
            # Now safe to proceed with deletions - validation has passed
            _remove_hosts_from_group(group_id, list(existing_host_ids - new_host_ids), identity.org_id)
            # Add hosts to the "ungrouped" group
            ungrouped_group = get_or_create_ungrouped_hosts_group_for_identity(identity)
            removed_group_id_list = [str(ungrouped_group.id)]
            _add_hosts_to_group(str(ungrouped_group.id), list(existing_host_ids - new_host_ids), identity.org_id)

        # Process host changes within the same session to ensure write_event_to_outbox works
        if group_patched and host_id_data is None:
            # If anything was updated, and the host list is not being replaced,
            # send update messages to existing hosts. Otherwise, wait until the host list is replaced
            # so we don't produce messages that will be instantly obsoleted.
            serialized_groups, host_id_list = _update_hosts_for_group_changes(
                list(existing_host_ids), [group_id], identity
            )
        elif new_host_ids is not None:
            # If host IDs were provided, we need to update the host list.
            # First, update the modified date for the group
            group.update_modified_on()
            db.session.add(group)

            # Handle removed hosts
            removed_host_uuids = [str(host_id) for host_id in (existing_host_ids - new_host_ids)]
            removed_serialized_groups, removed_host_id_list = _update_hosts_for_group_changes(
                removed_host_uuids, removed_group_id_list, identity
            )

            # Handle added and existing hosts
            added_host_uuids = [str(host_id) for host_id in new_host_ids]
            added_serialized_groups, added_host_id_list = _update_hosts_for_group_changes(
                added_host_uuids, [group_id], identity
            )

    # Send MQ messages after successful database commit
    if group_patched and host_id_data is None:
        if host_id_list is not None:
            _process_host_changes(host_id_list, serialized_groups, staleness, identity, event_producer)
    elif new_host_ids is not None:
        if removed_host_id_list is not None and removed_serialized_groups is not None:
            _process_host_changes(removed_host_id_list, removed_serialized_groups, staleness, identity, event_producer)
        if added_host_id_list is not None and added_serialized_groups is not None:
            _process_host_changes(added_host_id_list, added_serialized_groups, staleness, identity, event_producer)


def _update_group_update_time(group_id: str, org_id: str):
    group = get_group_by_id_from_db(group_id, org_id)
    group.update_modified_on()
    db.session.add(group)
    db.session.flush()


def get_group_using_host_id(host_id: str, org_id: str):
    assoc = (
        db.session.query(HostGroupAssoc)
        .filter(HostGroupAssoc.org_id == org_id, HostGroupAssoc.host_id == host_id)
        .one_or_none()
    )
    return get_group_by_id_from_db(str(assoc.group_id), org_id) if assoc else None


def get_or_create_ungrouped_hosts_group_for_identity(identity: Identity) -> Group:
    group = get_ungrouped_group(identity)

    # If the "ungrouped" Group exists, return it.
    if group is not None:
        return group

    # Otherwise, create the workspace
    workspace_id = rbac_create_ungrouped_hosts_workspace(identity)

    # Create "ungrouped" group for this org using group ID == workspace ID
    return add_group(
        group_name="Ungrouped Hosts",
        org_id=identity.org_id,
        account=identity.account_number,
        group_id=workspace_id,
        ungrouped=True,
    )


def get_ungrouped_group(identity: Identity) -> Group:
    ungrouped_group = Group.query.filter(Group.org_id == identity.org_id, Group.ungrouped.is_(True)).one_or_none()
    return ungrouped_group


def serialize_group(group: Group) -> dict:
    host_count = get_non_culled_hosts_count_in_group(group, group.org_id)
    return serialize_group_with_host_count(group, host_count)
