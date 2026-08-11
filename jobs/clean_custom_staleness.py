#!/usr/bin/env python3
"""
One-time cleanup job: delete custom staleness records that are effectively
identical to the system defaults (within ±1 hour / 3600 seconds for every
conventional field).

Over time some orgs have had rows written to the ``staleness`` table whose
three conventional_time_to_* values are all within one hour of the hard-coded
system defaults.  Those rows add unnecessary overhead to queries such as
host_reaper.py which iterates every staleness row to apply per-org filtering.
This job removes them so the system-default code path is used instead.

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
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.logging import get_logger
from app.logging import threadctx
from app.models import Staleness
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard
from lib.staleness import DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS

PROMETHEUS_JOB = "clean-custom-staleness"
LOGGER_NAME = "clean_custom_staleness"
COLLECTED_METRICS: tuple = ()
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"


def _build_equivalence_filter():
    """Return a SQLAlchemy filter expression that matches staleness rows whose
    conventional fields are all within the equivalence tolerance of system defaults.

    A row is considered equivalent to system defaults when every field satisfies:
        abs(field_value - system_default) < TOLERANCE
    i.e. the difference is *strictly less than* DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS.
    """
    tolerance = DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS
    return (
        func.abs(Staleness.conventional_time_to_stale - CONVENTIONAL_TIME_TO_STALE_SECONDS) < tolerance,
        func.abs(Staleness.conventional_time_to_stale_warning - CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
        < tolerance,
        func.abs(Staleness.conventional_time_to_delete - CONVENTIONAL_TIME_TO_DELETE_SECONDS) < tolerance,
    )


def run(logger: Logger, session: Session, application: FlaskApp) -> int:
    """Delete redundant custom staleness rows.

    Returns the number of rows deleted (0 in dry-run mode).
    """
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    with application.app.app_context():
        threadctx.request_id = None

        eq_filters = _build_equivalence_filter()
        candidates = session.query(Staleness).filter(*eq_filters).all()

        if not candidates:
            logger.info("No staleness rows found that are equivalent to system defaults. Nothing to do.")
            return 0

        logger.info(
            "Found %d staleness row(s) equivalent to system defaults (tolerance: ±%d seconds).",
            len(candidates),
            DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS,
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
            logger.info("DRY_RUN is enabled; no rows deleted.")
            return 0

        with session_guard(session, close=False):
            for row in candidates:
                session.delete(row)

        logger.info("Deleted %d staleness row(s) equivalent to system defaults.", len(candidates))
        return len(candidates)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    job_type = "Clean custom staleness"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup(COLLECTED_METRICS, PROMETHEUS_JOB)

    try:
        run(logger, session, application)
    except Exception as e:
        logger.exception("Job failed: %s", e)
        sys.exit(1)
    finally:
        session.close()
