from app.auth import get_current_identity
from app.instrumentation import get_control_rule
from app.instrumentation import log_group_delete_failed
from app.instrumentation import log_group_delete_succeeded
from app.logging import get_logger
from app.models import Group
from app.models import HostGroupAssoc
from lib.db import session_guard
from lib.host_delete import _deleted_by_this_query
from lib.metrics import delete_group_count
from lib.metrics import delete_group_processing_time


logger = get_logger(__name__)


def _remove_all_hosts_from_group(session, group):
    delete_query = session.query(HostGroupAssoc).filter(HostGroupAssoc.group_id == group.id)
    delete_query.delete(synchronize_session="fetch")


def _delete_group(session, group):
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


def delete_group_list(group_id_list, chunk_size):
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
