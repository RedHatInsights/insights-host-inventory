from collections.abc import Callable
from logging import Logger
from typing import Any

from flask_sqlalchemy.query import Query
from sqlalchemy.orm import Session

from app.models import Host
from app.queue.event_producer import EventProducer
from lib.host_delete import delete_hosts
from lib.host_repository import contains_no_incorrect_facts_filter
from lib.host_repository import extract_immutable_and_id_facts
from lib.host_repository import matches_at_least_one_canonical_fact_filter

__all__ = ("delete_duplicate_hosts",)


def find_matching_hosts(canonical_facts: dict[str, Any], query: Query) -> list[Host]:
    immutable_facts, id_facts = extract_immutable_and_id_facts(canonical_facts)

    # First search based on immutable ID facts.
    if immutable_facts and (existing_hosts := find_hosts_by_multiple_facts(immutable_facts, query)):
        return existing_hosts

    # Now search based on other ID facts
    # Dicts have been ordered since Python 3.7, so the priority ordering will be respected
    for target_key, target_value in id_facts.items():
        # Keep immutable facts in the search to prevent matching if they are different.
        target_facts = dict(immutable_facts, **{target_key: target_value})

        if existing_hosts := find_hosts_by_multiple_facts(target_facts, query):
            return existing_hosts

    return []  # This should never happen as we are searching by facts of existing host


def find_hosts_by_multiple_facts(canonical_facts: dict[str, str], query: Query) -> list[Host]:
    return (
        query.filter(
            (contains_no_incorrect_facts_filter(canonical_facts))
            & (matches_at_least_one_canonical_fact_filter(canonical_facts))
        )
        .order_by(Host.last_check_in.desc())
        .all()
    )


def delete_hosts_by_ids(
    host_ids: set[str],
    *,
    org_id: str,
    session: Session,
    dry_run: bool,
    logger: Logger,
    event_producer: EventProducer,
    notifications_event_producer: EventProducer,
    chunk_size: int,
    interrupt: Callable[[], bool],
) -> int:
    if dry_run:
        logger.info(f"Found {len(host_ids)} duplicates in the current batch")
        return len(host_ids)

    hosts_by_ids_query = session.query(Host).filter(Host.org_id == org_id, Host.id.in_(host_ids))
    deleted_count = len(
        list(
            delete_hosts(
                hosts_by_ids_query,
                event_producer,
                notifications_event_producer,
                chunk_size,
                interrupt,
                control_rule="DEDUP",
            )
        )
    )
    logger.info(f"Deleted {deleted_count} duplicates in the current batch")
    return deleted_count


def delete_duplicate_hosts(
    org_ids_session: Session,
    hosts_session: Session,
    misc_session: Session,
    chunk_size: int,
    logger: Logger,
    event_producer: EventProducer,
    notifications_event_producer: EventProducer,
    interrupt: Callable[[], bool] = lambda: False,
    dry_run: bool = True,
) -> int:
    total_deleted = 0
    hosts_query = hosts_session.query(Host)
    org_id_query = org_ids_session.query(Host.org_id).distinct(Host.org_id).order_by(Host.org_id)

    logger.info(f"Total number of hosts in inventory: {hosts_query.count()}")
    logger.info(f"Total number of org_ids in inventory: {org_id_query.count()}")

    org_id_list = org_id_query.limit(chunk_size).all()
    while len(org_id_list) > 0 and not interrupt():
        for org_id in org_id_list:
            actual_org_id = org_id[0]  # query.distinct() returns a tuple of all queried columns
            logger.info(f"Processing org_id: {actual_org_id}")

            duplicates_per_org = 0
            misc_query = misc_session.query(Host).filter(Host.org_id == actual_org_id)

            host_list = (
                hosts_query.filter(Host.org_id == actual_org_id)
                .order_by(Host.last_check_in.desc())
                .limit(chunk_size)
                .all()
            )
            while len(host_list) > 0 and not interrupt():
                # Process a batch of hosts
                duplicate_host_ids = set()
                for host in host_list:
                    canonical_facts = host.canonical_facts
                    logger.info(f"Find by canonical facts: {canonical_facts}")
                    matching_hosts = find_matching_hosts(canonical_facts, misc_query)

                    logger.info(f"Found {len(matching_hosts)} matching hosts ({len(matching_hosts) - 1} duplicates)")
                    if len(matching_hosts) > 1:
                        duplicate_host_ids.update([host.id for host in matching_hosts[1:]])

                if duplicate_host_ids:
                    deleted_count = delete_hosts_by_ids(
                        duplicate_host_ids,
                        org_id=actual_org_id,
                        session=misc_session,
                        dry_run=dry_run,
                        logger=logger,
                        event_producer=event_producer,
                        notifications_event_producer=notifications_event_producer,
                        chunk_size=chunk_size,
                        interrupt=interrupt,
                    )
                    duplicates_per_org += deleted_count

                host_list = (
                    hosts_query.filter(Host.org_id == actual_org_id, Host.last_check_in < host_list[-1].last_check_in)
                    .order_by(Host.last_check_in.desc())
                    .limit(chunk_size)
                    .all()
                )

                misc_session.expunge_all()

            logger.info(f"Found {duplicates_per_org} duplicates for org_id: {actual_org_id}")
            total_deleted += duplicates_per_org
            hosts_session.expunge_all()

        org_id_list = org_id_query.filter(Host.org_id > actual_org_id).limit(chunk_size).all()

    return total_deleted
