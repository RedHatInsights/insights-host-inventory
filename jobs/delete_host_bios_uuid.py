#!/usr/bin/python3
"""
Job to delete the bios_uuid field from a specific host.

This script removes the bios_uuid field from a host by setting it to NULL.
"""

import os
import sys
import uuid
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "inventory-delete-host-bios-uuid"
LOGGER_NAME = "delete-host-bios-uuid"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

# Host ID to target for bios_uuid deletion
TARGET_HOST_ID = os.environ.get("TARGET_HOST_ID", "")


def run(logger: Logger, session: Session, application: FlaskApp):
    """Delete bios_uuid field from the specified host."""
    with application.app.app_context():
        # Validate that TARGET_HOST_ID is provided
        if not TARGET_HOST_ID:
            logger.error("TARGET_HOST_ID environment variable is required but not provided")
            logger.error("Please set TARGET_HOST_ID to the UUID of the host to process")
            return

        logger.info(f"Starting job to delete bios_uuid field from host {TARGET_HOST_ID}")

        try:
            # Parse the target host ID to ensure it's a valid UUID
            host_uuid = uuid.UUID(TARGET_HOST_ID)
            logger.info(f"Target host UUID parsed successfully: {host_uuid}")
        except ValueError as e:
            logger.error(f"Invalid host ID format '{TARGET_HOST_ID}': {e}")
            logger.error("TARGET_HOST_ID must be a valid UUID")
            return

        # Query for the specific host
        host = session.query(Host).filter(Host.id == host_uuid).first()

        if not host:
            logger.warning(f"Host with ID {TARGET_HOST_ID} not found")
            return

        logger.info(f"Found host: ID={host.id}, org_id={host.org_id}, display_name={host.display_name}")

        # Check current bios_uuid value
        current_bios_uuid = host.bios_uuid
        logger.info(f"Current bios_uuid value: {current_bios_uuid}")

        if current_bios_uuid is None:
            logger.info("bios_uuid is already NULL, no action needed")
            return

        # Delete the bios_uuid field by setting it to NULL
        host.bios_uuid = None
        logger.info("Set bios_uuid to NULL")

        # Update the canonical_facts if it contains bios_uuid
        if host.canonical_facts and "bios_uuid" in host.canonical_facts:
            logger.info("Removing bios_uuid from canonical_facts")
            del host.canonical_facts["bios_uuid"]
            # Mark the JSONB field as modified so SQLAlchemy detects the change
            from sqlalchemy import orm

            orm.attributes.flag_modified(host, "canonical_facts")

        try:
            session.commit()
            logger.info(f"Successfully deleted bios_uuid field from host {TARGET_HOST_ID}")
        except Exception as e:
            logger.error(f"Error committing changes: {e}", exc_info=True)
            session.rollback()
            raise


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Delete host bios_uuid field"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, event_producer, _, _, application = job_setup(tuple(), PROMETHEUS_JOB)
    session.expire_on_commit = False
    with session_guard(session):
        run(logger, session, application)
