#!/usr/bin/env python3
"""
Job to delete all groups for org_ids that have no hosts.

Used to clean up orphaned "Ungrouped Hosts" (and any other) groups left behind
for empty orgs. Triggered via ClowdJobInvocation (CJI).

Environment variables:
    ORG_IDS           - (required) Comma-separated list of org_ids to process
    DRY_RUN=true      - Log what would be deleted without writing (default: true)
    SUSPEND_JOB=true  - Exit immediately as a safety gate (default: true)
"""

from __future__ import annotations

import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.logging import threadctx
from app.models import Group
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "delete-empty-org-groups"
LOGGER_NAME = "delete_empty_org_groups"
COLLECTED_METRICS: tuple = ()
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"


def _parse_org_ids(raw: str) -> list[str]:
    """Split a comma-separated ORG_IDS string into a de-duplicated ordered list."""
    seen: set[str] = set()
    org_ids: list[str] = []
    for part in raw.split(","):
        org_id = part.strip()
        if not org_id or org_id in seen:
            continue
        seen.add(org_id)
        org_ids.append(org_id)
    return org_ids


def run(logger: Logger, session: Session, application: FlaskApp) -> None:
    raw_org_ids = os.environ.get("ORG_IDS", "").strip()
    if not raw_org_ids:
        logger.error("ORG_IDS is required but not set or empty.")
        sys.exit(1)

    org_ids = _parse_org_ids(raw_org_ids)
    if not org_ids:
        logger.error("ORG_IDS contained no valid org_id values.")
        sys.exit(1)

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    with application.app.app_context():
        threadctx.request_id = None

        # Validate first: any org with hosts aborts the whole job before deletions.
        orgs_with_hosts = {
            row[0] for row in session.query(Host.org_id).filter(Host.org_id.in_(org_ids)).distinct().all()
        }
        if orgs_with_hosts:
            logger.error(
                "org_id(s) %s have host(s); refusing to delete groups. Exiting.",
                sorted(orgs_with_hosts),
            )
            sys.exit(1)

        for org_id in org_ids:
            groups = session.query(Group).filter(Group.org_id == org_id).all()
            if not groups:
                logger.info("org_id=%s has no groups to delete.", org_id)
                continue

            group_ids = [str(group.id) for group in groups]
            logger.info(
                "org_id=%s: will delete %d group(s): %s",
                org_id,
                len(groups),
                group_ids,
            )

        if dry_run:
            logger.info("DRY_RUN is enabled; no changes written.")
            return

        with session_guard(session, close=False):
            total_deleted = session.query(Group).filter(Group.org_id.in_(org_ids)).delete(synchronize_session=False)
        logger.info("Finished deleting groups. Total deleted: %d", total_deleted)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    job_type = "Delete empty org groups"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup(COLLECTED_METRICS, PROMETHEUS_JOB)

    try:
        run(logger, session, application)
    except Exception as e:
        logger.exception("Job failed: %s", e)
        sys.exit(1)
    finally:
        session.close()
