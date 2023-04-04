from typing import List

from sqlalchemy.orm.scoping import scoped_session

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
from lib.db import session_guard
from lib.host_delete import _deleted_by_this_query
from lib.host_repository import find_existing_host_by_id
from lib.metrics import delete_group_count
from lib.metrics import delete_group_processing_time
from lib.metrics import delete_host_group_count
from lib.metrics import delete_host_group_processing_time


logger = get_logger(__name__)


def add_hosts_to_group(group_id: str, host_id_list: List[str]):
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

    log_host_group_add_succeeded(logger, host_id_list, group_id)


def add_group(group_data) -> Group:
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
            add_hosts_to_group(created_group.id, host_id_list)

    # gets the ID of the group after it has been committed
    created_group = Group.query.filter((Group.name == group_name) & (Group.org_id == org_id)).one_or_none()

    return created_group


def _remove_all_hosts_from_group(session: scoped_session, group: Group):
    delete_query = session.query(HostGroupAssoc).filter(HostGroupAssoc.group_id == group.id)
    delete_query.delete(synchronize_session="fetch")


def _delete_host_group_assoc(session, assoc):
    # TODO: Produce Kafka message upon deletion; don't delete if Kafka is not available
    delete_query = session.query(HostGroupAssoc).filter(
        HostGroupAssoc.group_id == assoc.group_id, HostGroupAssoc.host_id == assoc.host_id
    )
    delete_query.delete(synchronize_session="fetch")
    assoc_deleted = _deleted_by_this_query(assoc)
    if assoc_deleted:
        delete_host_group_count.inc()
        delete_query.session.commit()
    else:
        delete_query.session.rollback()

    return assoc_deleted


def _delete_group(session: scoped_session, group: Group) -> bool:
    # First, remove all hosts from the requested group.
    _remove_all_hosts_from_group(session, group)

    # TODO: Produce Kafka message upon deletion; don't delete if Kafka is not available
    delete_query = session.query(Group).filter(Group.id == group.id)
    delete_query.delete(synchronize_session="fetch")
    group_deleted = _deleted_by_this_query(group)
    if group_deleted:
        delete_group_count.inc()
        delete_query.session.commit()
    else:
        delete_query.session.rollback()

    return group_deleted


def delete_group_list(group_id_list: List[str], chunk_size: int) -> int:
    deletion_count = 0
    select_query = Group.query.filter((Group.org_id == get_current_identity().org_id) & Group.id.in_(group_id_list))

    # Do this for one group at a time, because once we add Kafka integration,
    # we'll need to send a message for each group.
    # We may also need to send a message for each HostGroupAssoc that we remove.
    with session_guard(select_query.session):
        while select_query.count():
            for group in select_query.limit(chunk_size):
                with delete_group_processing_time.time():
                    if _delete_group(select_query.session, group):
                        deletion_count += 1
                        log_group_delete_succeeded(logger, group.id, get_control_rule())
                    else:
                        log_group_delete_failed(logger, group.id, get_control_rule())

    return deletion_count


def remove_hosts_from_group(group_id, host_id_list):
    deletion_count = 0
    group_query = Group.query.filter(Group.org_id == get_current_identity().org_id, Group.id == group_id)

    # First, find the group to make sure the org_id matches
    found_group = group_query.one_or_none()
    if not found_group:
        return 0

    host_group_query = HostGroupAssoc.query.filter(
        HostGroupAssoc.group_id == found_group.id, HostGroupAssoc.host_id.in_(host_id_list)
    )
    with session_guard(host_group_query.session), delete_host_group_processing_time.time():
        for assoc in host_group_query.all():
            if _delete_host_group_assoc(host_group_query.session, assoc):
                deletion_count += 1
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
    session: scoped_session, group: Group, host_id_list: List[str]
) -> List[HostGroupAssoc]:
    with session_guard(session):
        # TODO: Should we only remove hosts that aren't in host_id_list?
        # Does it really matter, since they'll immediately be recreated before the commit?
        _remove_all_hosts_from_group(session, group)
        assoc_list = []
        for host_id in host_id_list:
            if not find_existing_host_by_id(get_current_identity(), host_id):
                raise InventoryException(title="Invalid request", detail=f"Host with ID {host_id} does not exist.")

            assoc_list.append(db_create_host_group_assoc(host_id, group.id))
            # Update modified_on timestamp on the group
            group.update_modified_on()

    return assoc_list
