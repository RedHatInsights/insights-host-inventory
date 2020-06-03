from sqlalchemy.orm.base import instance_state

from app.events import delete as delete_event
from app.events import DELETE_EVENT_NAME
from app.events import hostname
from app.events import message_headers
from app.logging import threadctx
from app.models import Host
from lib.metrics import delete_host_count
from lib.metrics import delete_host_processing_time
from tasks import emit_event

__all__ = ("delete_hosts",)
CHUNK_SIZE = 1000


def delete_hosts(select_query):
    while select_query.count():
        for host in select_query.limit(CHUNK_SIZE):
            host_id = host.id
            with delete_host_processing_time.time():
                _delete_host(select_query.session, host)

            host_deleted = _deleted_by_this_query(host)
            if host_deleted:
                delete_host_count.inc()
                _emit_event(host)

            yield host_id, host_deleted


def _delete_host(session, host):
    delete_query = session.query(Host).filter(Host.id == host.id)
    delete_query.delete(synchronize_session="fetch")
    delete_query.session.commit()


def _deleted_by_this_query(host):
    # This process of checking for an already deleted host relies
    # on checking the session after it has been updated by the commit()
    # function and marked the deleted hosts as expired.  It is after this
    # change that the host is called by a new query and, if deleted by a
    # different process, triggers the ObjectDeletedError and is not emited.
    return not instance_state(host).expired


def _emit_event(host):
    event = delete_event(host)
    key = str(host.id)
    headers = message_headers(
        event_type=DELETE_EVENT_NAME,
        request_id=threadctx.request_id,
        producer=hostname(),
        registered_with_insights="true" if "insights_id" in host.canonical_facts else "false",
    )
    emit_event(event, key, headers)
