#!/usr/bin/python3
# ruff: noqa: E501
import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "simulate-replica-identity-error"
LOGGER_NAME = "simulate_replica_identity_error"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "false").lower() == "true"

HOSTS_PER_PARTITION = int(os.environ.get("HOSTS_PER_PARTITION", 1000))
TOTAL_PARTITIONS = int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 32))

"""
This job attempts to reproduce the replica identity error by updating a large
number of hosts across all 32 partitions in a production-like environment.

It targets a specific number of hosts from each partition and performs an
UPDATE on their `insights_id` column. This action is designed to trigger the
PostgreSQL logical replication checks that were failing in production.
"""


def perform_update(session: Session, logger: Logger):
    """
    Executes a large-scale UPDATE statement on the hosts table, targeting
    a specific number of hosts from every partition.
    """
    total_hosts_to_update = HOSTS_PER_PARTITION * TOTAL_PARTITIONS
    logger.info(
        f"Attempting to update {HOSTS_PER_PARTITION} hosts from each of the {TOTAL_PARTITIONS} partitions "
        f"(total: {total_hosts_to_update} hosts)..."
    )

    # Build a subquery that selects a limited number of IDs from each partition.
    # This ensures the update load is spread evenly across the entire table.
    selects = [
        f"(SELECT id FROM {INVENTORY_SCHEMA}.hosts_p{p} LIMIT {HOSTS_PER_PARTITION})" for p in range(TOTAL_PARTITIONS)
    ]
    subquery_from_clause = " UNION ALL ".join(selects)

    # This SQL statement uses the subquery to get a list of IDs to update.
    # We are updating insights_id because it is part of the publication's WHERE clause.
    sql_statement = f"""
        UPDATE {INVENTORY_SCHEMA}.hosts
        SET modified_on = NOW(),
            insights_id = gen_random_uuid()
        WHERE id IN (
            {subquery_from_clause}
        );
    """

    # The entire operation is one transaction. If it fails, nothing is committed.
    result = session.execute(text(sql_statement))
    logger.info(f"Successfully updated {result.rowcount} hosts. The error was not reproduced with this run.")


def run(logger: Logger, session: Session, application: FlaskApp):
    """Main execution function."""
    with application.app.app_context():
        # The session_guard ensures the entire operation is one atomic transaction.
        with session_guard(session):
            perform_update(session, logger)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)

    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    job_type = "Simulate Replica Identity Error"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    run(logger, session, application)
