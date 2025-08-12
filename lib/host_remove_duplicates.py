from collections.abc import Callable
from logging import Logger
from typing import Any

from flask_sqlalchemy.query import Query
from sqlalchemy.orm import Session

from app.common import inventory_config
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
    org_id_query = org_ids_session.query(Host.org_id)

    logger.info(f"Total number of hosts in inventory: {hosts_query.count()}")
    logger.info(f"Total number of org_ids in inventory: {org_id_query.distinct(Host.org_id).count()}")

    for org_id in org_id_query.distinct(Host.org_id).yield_per(chunk_size):
        actual_org_id = org_id[0]  # query.distinct() returns a tuple of all queried columns
        logger.info(f"Processing org_id: {actual_org_id}")

        unique_host_ids = set()
        duplicate_host_ids = set()
        misc_query = misc_session.query(Host).filter(Host.org_id == actual_org_id)

        def unique(host_list: list[Host]) -> None:
            unique_host_ids.add(host_list[0].id)
            logger.info(f"{host_list[0].id} is unique, total: {len(unique_host_ids)}")
            if len(host_list) > 1:
                for host_id in [h.id for h in host_list[1:] if h.id not in unique_host_ids]:
                    duplicate_host_ids.add(host_id)
                    logger.info(f"{host_id} is a potential duplicate, total: {len(duplicate_host_ids)}")

        for host in (
            hosts_query.filter(Host.org_id == actual_org_id).order_by(Host.last_check_in.desc()).yield_per(chunk_size)
        ):
            canonical_facts = host.canonical_facts
            logger.info(f"find by canonical facts: {canonical_facts}")
            matching_hosts = find_matching_hosts(canonical_facts, misc_query)

            unique(matching_hosts)

        hosts_session.expunge_all()
        misc_session.expunge_all()

        # delete duplicate hosts
        if dry_run:
            logger.info(f"Found {len(duplicate_host_ids)} duplicates for org_id: {actual_org_id}")
            total_deleted += len(duplicate_host_ids)
        else:
            if inventory_config().hbi_db_refactoring_use_old_table:
                # Old code: filter by ID only
                hosts_by_ids_query = misc_session.query(Host).filter(Host.id.in_(duplicate_host_ids))
            else:
                # New code: filter by org_id and ID
                hosts_by_ids_query = misc_session.query(Host).filter(
                    Host.org_id == actual_org_id, Host.id.in_(duplicate_host_ids)
                )
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
            logger.info(f"Deleted {deleted_count} hosts for org_id: {actual_org_id}")
            total_deleted += deleted_count

        misc_session.expunge_all()

        if interrupt():
            break

    return total_deleted
