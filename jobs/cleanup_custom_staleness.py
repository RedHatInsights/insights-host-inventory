#!/usr/bin/env python3
"""
Job to delete staleness rows whose values are essentially identical to system defaults.

Over time, some organisations may have accumulated staleness rows whose custom
values differ from the system defaults by less than one hour (3600 seconds) on
every conventional field. These rows are redundant because the system applies
the same defaults when no custom row exists.

This job is idempotent and safe to re-run. It only removes rows where ALL three
conventional fields are within the tolerance window; any row with at least one
field that differs by exactly one hour or more is left untouched.

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
from lib.staleness import DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS

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


def _is_near_default(row: Staleness) -> bool:
    """Return True if every conventional field is strictly less than one hour from system defaults.

    A difference of exactly DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS (3600 s) or more
    on any field means the row is NOT near-default and must be kept.
    """
    for field in STALENESS_FIELDS:
        value = getattr(row, field)
        if abs(value - SYSTEM_DEFAULTS[field]) >= DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS:
            return False
    return True


def run(logger: Logger, session: Session, application: FlaskApp) -> None:
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    with application.app.app_context():
        threadctx.request_id = None

        rows = session.query(Staleness).all()
        near_default_rows = [row for row in rows if _is_near_default(row)]

        logger.info(
            "Found %d staleness row(s) total; %d are near-default and will be %s.",
            len(rows),
            len(near_default_rows),
            "logged only (DRY_RUN)" if dry_run else "deleted",
        )

        for row in near_default_rows:
            logger.info(
                "org_id=%s: near-default staleness row "
                "(stale=%d, warning=%d, delete=%d) — %s.",
                row.org_id,
                row.conventional_time_to_stale,
                row.conventional_time_to_stale_warning,
                row.conventional_time_to_delete,
                "would be deleted" if dry_run else "deleting",
            )

        if dry_run:
            logger.info("DRY_RUN is enabled; no changes written.")
            return

        deleted_count = 0
        for row in near_default_rows:
            org_id = row.org_id
            with session_guard(session, close=False):
                session.delete(row)
            deleted_count += 1
            logger.info("Deleted near-default staleness row for org_id=%s", org_id)

            try:
                StalenessCache.delete(org_id)
                logger.info("Invalidated staleness cache for org_id=%s", org_id)
            except Exception:
                logger.exception(
                    "Failed to invalidate cache for org_id=%s (DB write already committed)", org_id
                )

        logger.info("Finished cleanup. Deleted %d near-default staleness row(s).", deleted_count)


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
