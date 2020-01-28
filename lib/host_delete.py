from sqlalchemy.orm.base import instance_state

from api.metrics import delete_host_count
from api.metrics import delete_host_processing_time
from app.events import delete as delete_event
from tasks import emit_event


__all__ = ("delete_hosts",)


def delete_hosts(query):
    hosts_to_delete = query.all()
    if not hosts_to_delete:
        return None

    with delete_host_processing_time.time():
        query.delete(synchronize_session="fetch")
    query.session.commit()

    delete_host_count.inc(len(hosts_to_delete))

    return _emit_events(hosts_to_delete)


def _emit_events(deleted_hosts):
    # This process of checking for an already deleted host relies
    # on checking the session after it has been updated by the commit()
    # function and marked the deleted hosts as expired.  It is after this
    # change that the host is called by a new query and, if deleted by a
    # different process, triggers the ObjectDeletedError and is not emited.
    for deleted_host in deleted_hosts:
        # Prevents ObjectDeletedError from being raised.
        if instance_state(deleted_host).expired:
            # Not yielding the host. Accessing any attribute would raise ObjectDeletedError.
            yield None
        else:
            event = delete_event(deleted_host)
            emit_event(event)
            yield deleted_host
