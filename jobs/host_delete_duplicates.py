#!/usr/bin/python3

# mypy: disallow-untyped-defs

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from functools import partial
from logging import Logger
from typing import Any

from connexion import FlaskApp
from flask_sqlalchemy.query import Query
from sqlalchemy.orm import Session

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.queue.event_producer import EventProducer
from app.serialization import serialize_canonical_facts
from jobs.common import excepthook
from jobs.common import job_setup
from lib.handlers import ShutdownHandler
from lib.host_delete import delete_hosts
from lib.host_repository import contains_no_incorrect_facts_filter
from lib.host_repository import extract_immutable_and_id_facts
from lib.host_repository import matches_at_least_one_canonical_fact_filter
from lib.metrics import delete_duplicate_host_count

__all__ = ("run",)

PROMETHEUS_JOB = "duplicate-hosts-remover"
LOGGER_NAME = "duplicate-hosts-remover"
COLLECTED_METRICS = (delete_duplicate_host_count,)
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"


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


def delete_batch(
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
    deleted_count = sum(
        1
        for _ in delete_hosts(
            hosts_by_ids_query,
            event_producer,
            notifications_event_producer,
            chunk_size,
            interrupt,
            control_rule="DEDUP",
        )
    )
    logger.info(f"Deleted {deleted_count} duplicates in the current batch")
    return deleted_count


def delete_duplicate_hosts_by_org_id(
    org_id: str,
    *,
    session: Session,
    chunk_size: int,
    logger: Logger,
    event_producer: EventProducer,
    notifications_event_producer: EventProducer,
    interrupt: Callable[[], bool] = lambda: False,
    dry_run: bool = True,
) -> int:
    logger.info(f"Processing org: {org_id}")
    deleted_per_org = 0
    hosts_query = session.query(Host).filter(Host.org_id == org_id)
    host_list = hosts_query.order_by(Host.id).limit(chunk_size).all()

    while len(host_list) > 0 and not interrupt():
        # Process a batch of hosts
        duplicate_host_ids = set()
        last_host_id = host_list[-1].id  # Needed in case this host gets deleted

        for host in host_list:
            canonical_facts = serialize_canonical_facts(host)
            logger.info(f"Find by canonical facts: {canonical_facts}")
            matching_hosts = find_matching_hosts(canonical_facts, hosts_query)

            logger.info(
                f"Found {len(matching_hosts)} matching hosts ({len(matching_hosts) - 1} duplicates) "
                f"for host: {host.id}"
            )
            if len(matching_hosts) > 1:
                duplicate_host_ids.update([host.id for host in matching_hosts[1:]])

        if duplicate_host_ids:
            deleted_per_org += delete_batch(
                duplicate_host_ids,
                org_id=org_id,
                session=session,
                dry_run=dry_run,
                logger=logger,
                event_producer=event_producer,
                notifications_event_producer=notifications_event_producer,
                chunk_size=chunk_size,
                interrupt=interrupt,
            )

        host_list = hosts_query.filter(Host.id > last_host_id).order_by(Host.id).limit(chunk_size).all()

    if dry_run:
        logger.info(f"Found {deleted_per_org} duplicates in org: {org_id}")
    else:
        logger.info(f"Deleted {deleted_per_org} duplicates in org: {org_id}")

    return deleted_per_org


def delete_duplicate_hosts(
    session: Session,
    chunk_size: int,
    logger: Logger,
    event_producer: EventProducer,
    notifications_event_producer: EventProducer,
    interrupt: Callable[[], bool] = lambda: False,
    dry_run: bool = True,
) -> int:
    total_deleted = 0
    org_ids_query = session.query(Host.org_id)

    logger.info(f"Total number of hosts in inventory: {session.query(Host).count()}")
    logger.info(f"Total number of org_ids in inventory: {org_ids_query.distinct().count()}")

    org_id_list = org_ids_query.distinct().order_by(Host.org_id).all()
    for org_id in org_id_list:
        actual_org_id = org_id[0]  # query.distinct() returns a tuple of all queried columns
        total_deleted += delete_duplicate_hosts_by_org_id(
            actual_org_id,
            session=session,
            chunk_size=chunk_size,
            logger=logger,
            event_producer=event_producer,
            notifications_event_producer=notifications_event_producer,
            interrupt=interrupt,
            dry_run=dry_run,
        )

        session.expunge_all()

    return total_deleted


def run(
    config: Config,
    logger: Logger,
    session: Session,
    event_producer: EventProducer,
    notifications_event_producer: EventProducer,
    shutdown_handler: ShutdownHandler,
    application: FlaskApp,
) -> int | None:
    if config.dry_run:
        logger.info(f"Running {PROMETHEUS_JOB} in dry-run mode. Duplicate hosts will NOT be deleted.")
    else:
        logger.info(f"Running {PROMETHEUS_JOB} without dry-run. Duplicate hosts WILL be deleted.")

    with application.app.app_context():
        threadctx.request_id = None
        try:
            num_deleted = delete_duplicate_hosts(
                session,
                config.script_chunk_size,
                logger,
                event_producer,
                notifications_event_producer,
                shutdown_handler.shut_down,
                dry_run=config.dry_run,
            )

            if config.dry_run:
                logger.info(
                    f"This was a dry run. This many hosts would have been deleted in an actual run: {num_deleted}"
                )
            else:
                logger.info(f"This was NOT a dry run. Total number of deleted hosts: {num_deleted}")

            return num_deleted

        except InterruptedError:
            logger.info(f"{PROMETHEUS_JOB} was interrupted.")
            return None
        except Exception as e:
            logger.exception(e)
            return None
        finally:
            session.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    job_type = "Delete duplicate hosts"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, event_producer, notifications_event_producer, shutdown_handler, application = job_setup(
        COLLECTED_METRICS, PROMETHEUS_JOB
    )

    run(
        config,
        logger,
        session,
        event_producer,
        notifications_event_producer,
        shutdown_handler,
        application,
    )
