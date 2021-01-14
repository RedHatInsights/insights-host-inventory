from sqlalchemy.orm.base import instance_state

from app.logging import get_logger
from app.models import Host
from app.queue.event_producer import Topic
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from lib.metrics import delete_host_count
from lib.metrics import delete_host_processing_time

logger = get_logger(__name__)

__all__ = ("delete_hosts",)


def _commit_delete(delete_query=None):
    if delete_query is None:
        logger.debug("BEANS")
        return
    logger.debug("commmited delete")
    delete_host_count.inc()
    delete_query.session.commit()


def _rollback_delete(delete_query):
    logger.debug("Rolled back delete")
    delete_query.session.rollback()


def delete_hosts(select_query, event_producer, chunk_size, interrupt=lambda: False):
    # Check if Kafka is up here, return 500 if it's down
    # else continue
    # check kafka by querying the topics on Kafka
    # if not event_producer.kafka_up():
    #     flask.abort(500)
    while select_query.count():
        for host in select_query.limit(chunk_size):
            host_id = host.id
            with delete_host_processing_time.time():
                # _delete_host(select_query.session, host)
                # host_deleted = _deleted_by_this_query(host)

                # create the query
                delete_query = select_query.session.query(Host).filter(Host.id == host.id)
                # initiate the delete
                delete_query.delete(synchronize_session="fetch")

                # Check if the query has succeeded
                host_deleted_in_db = _deleted_by_this_query(host)

                if host_deleted_in_db:
                    logger.debug("deleted in db (not commited)")
                    event = build_event(EventType.delete, host)
                    insights_id = host.canonical_facts.get("insights_id")
                    headers = message_headers(EventType.delete, insights_id)
                    event_producer.write_event(
                        event,
                        str(host.id),
                        headers,
                        Topic.events,
                        wait=True,
                        extra_callback=_commit_delete,
                        # extra_callback_parameters={"delete_query": delete_query},
                        extra_callback_parameters={"beans": delete_query},
                        extra_errback=_rollback_delete,
                        extra_errback_parameters={"delete_query": delete_query},
                    )

            yield host_id, host_deleted_in_db
            if interrupt():
                return


# def _delete_host(session, host):
#     delete_query = session.query(Host).filter(Host.id == host.id)
#     delete_query.delete(synchronize_session="fetch")
#     delete_query.session.commit()


def _deleted_by_this_query(host):
    # This process of checking for an already deleted host relies
    # on checking the session after it has been updated by the commit()
    # function and marked the deleted hosts as expired.  It is after this
    # change that the host is called by a new query and, if deleted by a
    # different process, triggers the ObjectDeletedError and is not emited.
    logger.debug("checking if delete succeeded")
    return not instance_state(host).expired
