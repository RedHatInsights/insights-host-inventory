#!/usr/bin/env python3
"""
Job to delete custom staleness rows that are functionally equivalent to system defaults.

Over time, custom staleness records accumulate in the `staleness` table for org IDs
whose values are within ±TOLERANCE of the system defaults. These redundant rows bloat
the table and cause unnecessary cache lookups / joins in the host-reaper path.

This job identifies and removes those near-default rows and invalidates their cache entries.

Environment variables:
    CLEANUP_STALENESS_TOLERANCE - Tolerance in seconds (default: 3600)
    DRY_RUN=true               - Log what would be deleted without writing (default: true)
    SUSPEND_JOB=true           - Exit immediately as a safety gate (default: true)
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


def _is_near_default(row: Staleness, tolerance: int) -> bool:
    """Return True if all staleness fields on `row` are within `tolerance` of the system defaults."""
    for field in STALENESS_FIELDS:
        value = getattr(row, field)
        default = SYSTEM_DEFAULTS[field]
        if abs(value - default) > tolerance:
            return False
    return True


def run(logger: Logger, session: Session, application: FlaskApp) -> None:
    tolerance_raw = os.environ.get("CLEANUP_STALENESS_TOLERANCE", "3600")
    try:
        tolerance = int(tolerance_raw)
    except ValueError:
        logger.error("CLEANUP_STALENESS_TOLERANCE must be an integer, got: %r", tolerance_raw)
        sys.exit(1)

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    with application.app.app_context():
        threadctx.request_id = None

        all_rows = session.query(Staleness).all()
        candidates = [row for row in all_rows if _is_near_default(row, tolerance)]

        if not candidates:
            logger.info("No near-default staleness rows found. Nothing to do.")
            return

        logger.info(
            "Found %d near-default staleness row(s) (tolerance=%d s):",
            len(candidates),
            tolerance,
        )
        for row in candidates:
            logger.info(
                "  org_id=%s: stale=%d, warning=%d, delete=%d",
                row.org_id,
                row.conventional_time_to_stale,
                row.conventional_time_to_stale_warning,
                row.conventional_time_to_delete,
            )

        if dry_run:
            logger.info("DRY_RUN is enabled; no changes written.")
            return

        candidate_ids = [row.id for row in candidates]
        candidate_org_ids = [row.org_id for row in candidates]

        with session_guard(session, close=False):
            session.query(Staleness).filter(Staleness.id.in_(candidate_ids)).delete(synchronize_session=False)

        logger.info("Deleted %d near-default staleness row(s).", len(candidate_ids))

        for org_id in candidate_org_ids:
            try:
                StalenessCache.delete(org_id)
                logger.info("Invalidated staleness cache for org_id=%s", org_id)
            except Exception:
                logger.exception("Failed to invalidate cache for org_id=%s (DB delete succeeded)", org_id)


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
