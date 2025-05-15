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
from app.models import Group
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "inventory-export-groups-s3"
LOGGER_NAME = "export_groups_s3"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
S3_OBJECT_KEY = "groups_data.csv"
GROUPS_BATCH_SIZE = 500


def get_s3_client(config: Config):
    """Create and return an S3 client."""
    return boto3.client(
        "s3",
        aws_access_key_id=config.s3_access_key_id,
        aws_secret_access_key=config.s3_secret_access_key,
    )


def run(config: Config, logger: Logger, session: Session, application: FlaskApp):
    with application.app.app_context():
        try:
            logger.info(f"Running Groups data export with batch size {GROUPS_BATCH_SIZE}")
            s3_client = get_s3_client(config)
            csv_buffer = StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow([column.name for column in Group.__mapper__.columns])

            for group in session.query(Group).yield_per(GROUPS_BATCH_SIZE):
                # Write the CSV group data
                writer.writerow([getattr(group, column.name) for column in Group.__mapper__.columns])
                logger.debug(f"Successfully wrote CSV for group {str(group.id)}")

            # Put CSV in s3 bucket
            s3_client.put_object(Body=csv_buffer.getvalue(), Bucket=config.s3_bucket, Key=S3_OBJECT_KEY)
            logger.info(f"Successfully exported group data into bucket {config.s3_bucket} with key {S3_OBJECT_KEY}!")

        except Exception as e:
            logger.exception(e)
        finally:
            s3_client.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Create ungrouped host groups"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup(tuple(), PROMETHEUS_JOB)
    run(config, logger, session, application)
