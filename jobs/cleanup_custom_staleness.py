#!/usr/bin/env python3
"""
Job to scan every row in the staleness table and delete records whose
conventional staleness values are all within one hour (< 3600 seconds
absolute difference) of the system defaults.

Such rows are redundant because HBI already falls back to system defaults
when no custom staleness row exists for an org.

Environment variables:
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

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.logging import get_logger
from app.logging import threadctx
from app.models import Staleness
from app.models.utils import StalenessCache
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "cleanup-custom-staleness"
LOGGER_NAME = "cleanup_custom_staleness"
COLLECTED_METRICS: tuple = ()
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"
TOLERANCE_SECONDS = 3600

SYSTEM_DEFAULTS = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
}

STALENESS_FIELDS = (
    "conventional_time_to_stale",
    "conventional_time_to_stale_warning",
    "conventional_time_to_delete",
)


def _is_near_default(row: Staleness) -> bool:
    """Return True if all staleness fields are within TOLERANCE_SECONDS of system defaults."""
    return all(abs(getattr(row, field) - SYSTEM_DEFAULTS[field]) < TOLERANCE_SECONDS for field in STALENESS_FIELDS)


def run(
    logger: Logger,
    session: Session,
    application: FlaskApp,
) -> None:
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    with application.app.app_context():
        threadctx.request_id = None

        rows = session.query(Staleness).all()
        deleted = 0
        retained = 0

        near_default_rows = []
        for row in rows:
            if _is_near_default(row):
                logger.info("org_id=%s is eligible for deletion (near-default staleness values)", row.org_id)
                near_default_rows.append(row)
            else:
                retained += 1

        if dry_run:
            logger.info("DRY_RUN is enabled; no changes written.")
        elif near_default_rows:
            with session_guard(session, close=False):
                for row in near_default_rows:
                    session.delete(row)
            for row in near_default_rows:
                StalenessCache.delete(row.org_id)
            deleted = len(near_default_rows)

        logger.info(
            "Summary: total=%d scanned, deleted=%d, retained=%d",
            len(rows),
            deleted,
            retained,
        )


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    job_type = "Cleanup custom staleness"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup(COLLECTED_METRICS, PROMETHEUS_JOB)

    try:
        run(logger, session, application)
    except Exception as e:
        logger.exception("Job failed: %s", e)
        sys.exit(1)
    finally:
        session.close()
