from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import array

from app.instrumentation import log_host_delete_succeeded
from app.models import Host
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from lib.metrics import delete_duplicate_host_count

__all__ = ("delete_duplicate_hosts",)

ELEVATED_CANONICAL_FACT_FIELDS = ("provider_id", "insights_id", "subscription_manager_id")


def matches_at_least_one_canonical_fact_filter(canonical_facts):
    # Contains at least one correct CF value
    # Correct value = contains key:value
    # -> OR( *correct values )
    return or_(Host.canonical_facts.contains({key: value}) for key, value in canonical_facts.items())


def contains_no_incorrect_facts_filter(canonical_facts):
    # Does not contain any incorrect CF values
    # Incorrect value = AND( key exists, NOT( contains key:value ) )
    # -> NOT( OR( *Incorrect values ) )
    filter_ = ()
    for key, value in canonical_facts.items():
        filter_ += (
            and_(Host.canonical_facts.has_key(key), not_(Host.canonical_facts.contains({key: value}))),  # noqa: W601
        )

    return not_(or_(*filter_))


def multiple_canonical_facts_host_query(canonical_facts, query):
    query = query.filter(
        (contains_no_incorrect_facts_filter(canonical_facts))
        & (matches_at_least_one_canonical_fact_filter(canonical_facts))
    )
    return query


def contains_no_elevated_facts_query(query):
    return query.filter(not_(Host.canonical_facts.has_any(array(ELEVATED_CANONICAL_FACT_FIELDS))))


# Get hosts by the highest elevated canonical fact present
def find_host_list_by_elevated_canonical_facts(elevated_cfs, query, logger):
    """
    First check if multiple hosts are returned.  If they are then retain the one with the highest
    priority elevated fact
    """
    logger.debug("find_host_by_elevated_canonical_facts(%s)", elevated_cfs)

    if elevated_cfs.get("provider_id"):
        elevated_cfs.pop("subscription_manager_id", None)
        elevated_cfs.pop("insights_id", None)
    elif elevated_cfs.get("insights_id"):
        elevated_cfs.pop("subscription_manager_id", None)

    hosts = multiple_canonical_facts_host_query(elevated_cfs, query).order_by(Host.modified_on.desc()).all()

    return hosts


# this function is called when no elevated canonical facts are present in the host
def find_host_list_by_regular_canonical_facts(canonical_facts, query, logger):
    """
    Returns all matches for a host containing given canonical facts
    """
    logger.debug("find_host_by_regular_canonical_facts(%s)", canonical_facts)

    hosts = (
        contains_no_elevated_facts_query(multiple_canonical_facts_host_query(canonical_facts, query))
        .order_by(Host.modified_on.desc())
        .all()
    )
    return hosts


def _delete_hosts_by_id_list(session, host_id_list):
    delete_query = session.query(Host).filter(Host.id.in_(host_id_list))
    delete_query.delete(synchronize_session="fetch")
    delete_query.session.commit()


def delete_duplicate_hosts(
    org_ids_session, hosts_session, misc_session, chunk_size, logger, event_producer, interrupt=lambda: False
):
    total_deleted = 0
    hosts_query = hosts_session.query(Host)
    org_id_query = org_ids_session.query(Host.org_id)

    logger.info(f"Total number of hosts in inventory: {hosts_query.count()}")
    logger.info(f"Total number of org_ids in inventory: {org_id_query.distinct(Host.org_id).count()}")

    for org_id in org_id_query.distinct(Host.org_id).yield_per(chunk_size):
        logger.info(f"Processing org_id {org_id}")
        unique_list = list()
        duplicate_list = list()
        misc_query = misc_session.query(Host).filter(Host.org_id == org_id)

        def unique(host_list):
            if host_list[0].id not in unique_list:
                unique_list.append(host_list[0].id)
                logger.info(f"{host_list[0].id} is unique, total: {len(unique_list)}")
            if len(host_list) > 1:
                for host_id in [h.id for h in host_list[1:] if h.id not in unique_list and h.id not in duplicate_list]:
                    duplicate_list.append(host_id)
                    logger.info(f"{host_id} is a potential duplicate")

        for host in hosts_query.filter(Host.org_id == org_id).order_by(Host.modified_on.desc()).yield_per(chunk_size):
            canonical_facts = host.canonical_facts
            elevated_cfs = {
                key: value for key, value in canonical_facts.items() if key in ELEVATED_CANONICAL_FACT_FIELDS
            }
            if elevated_cfs:
                logger.info(f"find by elevated canonical facts: {elevated_cfs}")
                host_matches = find_host_list_by_elevated_canonical_facts(elevated_cfs, misc_query, logger)
            else:
                regular_cfs = {
                    key: value for key, value in canonical_facts.items() if key not in ELEVATED_CANONICAL_FACT_FIELDS
                }
                logger.info(f"find by regular canonical facts: {regular_cfs}")
                if regular_cfs:
                    host_matches = find_host_list_by_regular_canonical_facts(regular_cfs, misc_query, logger)

            unique(host_matches)
            hosts_session.expunge_all()
        org_ids_session.expunge_all()

        # delete duplicate hosts
        _delete_hosts_by_id_list(misc_session, duplicate_list)
        for host_id in duplicate_list:
            log_host_delete_succeeded(logger, host_id, "DEDUP")
            delete_duplicate_host_count.inc()
            event = build_event(EventType.delete, host)
            headers = message_headers(
                EventType.delete,
                host.canonical_facts.get("insights_id"),
                host.reporter,
                host.system_profile_facts.get("host_type"),
                host.system_profile_facts.get("operating_system", {}).get("name"),
                str(host.system_profile_facts.get("bootc_status", {}).get("booted") is not None),
            )
            # add back "wait=True", if needed.
            event_producer.write_event(event, str(host.id), headers, wait=True)

        total_deleted += len(duplicate_list)

    return total_deleted
