#!/usr/bin/python
import csv
import sys
from functools import partial
from io import StringIO
from logging import Logger

import boto3
from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "inventory-delete-hosts-s3"
LOGGER_NAME = "delete_hosts_s3"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
S3_OBJECT_KEY = "host_ids.csv"
BATCH_SIZE = 500

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
    )


def process_batch(batch: list[str], session: Session, config: Config, logger: Logger):
    """
    Processes a batch of host IDs and deletes hosts with only one reporter.

    This function retrieves hosts from the database whose IDs are in the provided batch.
    Hosts with only one reporter are deleted unless in dry-run mode. The function updates
    counters for deleted, not deleted, and not found hosts. After processing, changes are
    committed to the database if not in dry-run mode.

    Args:
        batch (list[str]): List of host IDs to process.
        session (Session): SQLAlchemy session for database operations.
        config (Config): Application configuration object.
        logger (Logger): Logger for logging information.
    """
    global deleted_count, not_deleted_count, not_found_count
    with session_guard(session):
        logger.info(f"Processing batch of {len(batch)} host IDs...")
        host_list = session.query(Host).filter(Host.id.in_(batch)).all()
        not_found_count += len(batch) - len(host_list)

        for host in host_list:
            # Check whether there's another reporter. If so, increment a counter; otherwise, delete it
            if len(host.per_reporter_staleness) > 1:
                not_deleted_count += 1
            else:
                # Delete the host if it's not in dry-run mode
                if not config.dry_run:
                    session.delete(host)
                deleted_count += 1

        # Commit deletions if not in dry-run mode
        if not config.dry_run:
            session.commit()


def run(config: Config, logger: Logger, session: Session, application: FlaskApp):
    """
    Runs the host deletion job using host IDs from a CSV file in an S3 bucket.

    This function reads host IDs from a CSV file stored in S3, processes them in batches,
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

            # Read the CSV data from the S3 bucket one batch at a time
            s3_object = s3_client.get_object(Bucket=config.s3_bucket, Key=S3_OBJECT_KEY)
            csv_stream = StringIO(s3_object["Body"].read().decode("utf-8"))
            reader = csv.reader(csv_stream)

            batch = []
            for row in reader:
                if not row:
                    continue
                batch.append(row[0])
                if len(batch) == BATCH_SIZE:
                    # The batch is now full, so we should process the hosts in the batch.
                    process_batch(batch, session, config, logger)

                    # Empty the batch and start again
                    batch = []

            # If the reader ran out of rows, process that final batch
            if batch:
                process_batch(batch, session, config, logger)

            logger.info(f"Hosts that were not deleted because they had multiple reporters: {not_deleted_count}")
            logger.info(f"Hosts whose IDs were not found in the DB: {not_found_count}")
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

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)
    run(config, logger, session, application)
