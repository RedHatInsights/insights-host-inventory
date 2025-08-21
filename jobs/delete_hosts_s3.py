#!/usr/bin/python3
import csv
import io
import os
import sys
from functools import partial
from logging import Logger

import boto3
from botocore.config import Config as BotoConfig
from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.queue.event_producer import EventProducer
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard
from lib.host_delete import delete_hosts

PROMETHEUS_JOB = "inventory-delete-hosts-s3"
LOGGER_NAME = "delete_hosts_s3"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
S3_OBJECT_KEY = "host_ids.csv"
BATCH_SIZE = int(os.getenv("DELETE_HOSTS_S3_BATCH_SIZE", 500))
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"


# Vars to keep track of the number of hosts deleted, not deleted, and not found
deleted_count = 0
not_deleted_count = 0
not_found_count = 0


def get_s3_client(config: Config):
    """Create and return an S3 client."""
    return boto3.client(
        "s3",
        aws_access_key_id=config.s3_access_key_id,
        aws_secret_access_key=config.s3_secret_access_key,
        config=BotoConfig(retries={"mode": "standard", "total_max_attempts": 20}),
    )


def process_batch(
    batch: list[str],
    config: Config,
    logger: Logger,
    session: Session,
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
):
    """
    Processes a batch of Subscription Manager IDs and deletes hosts with only one reporter.

    This function retrieves hosts from the database whose IDs are in the provided batch.
    Hosts with only one reporter are deleted unless in dry-run mode. The function updates
    counters for deleted, not deleted, and not found hosts. After processing, changes are
    committed to the database if not in dry-run mode.

    Args:
        batch (list[str]): List of Subscription Manager IDs to process.
        session (Session): SQLAlchemy session for database operations.
        config (Config): Application configuration object.
        logger (Logger): Logger for logging information.
    """
    if not batch:
        logger.info("Received empty batch, skipping.")
        return

    global deleted_count, not_deleted_count, not_found_count
    with session_guard(session):
        logger.info(f"Processing batch of {len(batch)} Subscription Manager IDs...")
        batch_hosts = (
            session.query(Host).filter(Host.canonical_facts["subscription_manager_id"].astext.in_(batch)).all()
        )

        # The difference in length tells us how many were not found.
        not_found_count += len(batch) - len(batch_hosts)

        # Get the IDs of the hosts that only have 1 reporter.
        host_ids_to_delete = [host.id for host in batch_hosts if len(host.per_reporter_staleness) == 1]

        # The difference in length tells us how many we *aren't* deleting.
        not_deleted_count += len(batch_hosts) - len(host_ids_to_delete)

        # Make the query filtered on the host IDs.
        delete_query = session.query(Host).filter(Host.id.in_(host_ids_to_delete))

        if config.dry_run:
            # If it's a dry run, just get the count of matching hosts.
            deleted_count += delete_query.count()
        else:
            # If it's a real run, delete the hosts (and add to the count).
            deleted_count += sum(
                1 for _ in delete_hosts(delete_query, event_producer, notification_event_producer, BATCH_SIZE)
            )


def run(
    config: Config,
    logger: Logger,
    session: Session,
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    application: FlaskApp,
):
    """
    Runs the host deletion job using Subscription Manager IDs from a CSV file in an S3 bucket.

    This function reads Subscription Manager IDs from a CSV file stored in S3, processes them in batches,
    and deletes hosts with only one reporter from the database unless in dry-run mode.
    It logs the results of the deletion process, including counts of deleted, not deleted,
    and not found hosts.

    Args:
        config (Config): Application configuration object.
        logger (Logger): Logger for logging information.
        session (Session): SQLAlchemy session for database operations.
        application (FlaskApp): The Flask application instance.
    """
    with application.app.app_context():
        try:
            logger.info(f"Running host_delete_s3 with batch size {BATCH_SIZE}")
            s3_client = get_s3_client(config)

            # Download the entire CSV file from S3 first
            logger.info("Downloading CSV file from S3...")
            s3_object = s3_client.get_object(Bucket=config.s3_bucket, Key=S3_OBJECT_KEY)
            # Download the entire file content
            csv_content = s3_object["Body"].read().decode("utf-8")
            logger.info(f"Downloaded CSV file, size: {len(csv_content)} bytes")

            # Create a file-like object from the downloaded content
            csv_stream = io.StringIO(csv_content)
            reader = csv.reader(csv_stream, delimiter="\t")

            # Skip the header row
            try:
                next(reader)
            except StopIteration:
                logger.warning("CSV file is empty.")
                return

            batch = []
            for row in reader:
                if not row:
                    continue
                batch.append(row[0])
                if len(batch) == BATCH_SIZE:
                    # The batch is now full, so we should process the hosts in the batch.
                    process_batch(batch, config, logger, session, event_producer, notification_event_producer)

                    # Empty the batch and start again
                    batch = []

            # If the reader ran out of rows, process that final batch
            if batch:
                process_batch(batch, config, logger, session, event_producer, notification_event_producer)

            logger.info(f"Hosts that were not deleted because they had multiple reporters: {not_deleted_count}")
            logger.info(f"Hosts whose Subscription Manager IDs were not found in the DB: {not_found_count}")
            if config.dry_run:
                logger.info(
                    f"This was a dry run. This many hosts would have been deleted in an actual run: {deleted_count}"
                )
            else:
                logger.info(f"This was NOT a dry run. Hosts that were actually deleted: {deleted_count}")

        except Exception as e:
            logger.exception(e)
        finally:
            s3_client.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Delete host IDs via S3"
    sys.excepthook = partial(excepthook, logger, job_type)
    threadctx.request_id = None

    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    config, session, event_producer, notification_event_producer, _, application = job_setup((), PROMETHEUS_JOB)
    run(config, logger, session, event_producer, notification_event_producer, application)
