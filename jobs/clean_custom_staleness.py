#!/usr/bin/env python3
"""
Job to delete custom staleness rows that are effectively identical to system defaults.

Rows where every conventional field differs from the system default by **strictly less**
than one hour (3600 seconds) are treated as equivalent to system defaults and are
redundant.  This is a one-time retroactive sweep of the staleness table.

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
from lib.staleness import staleness_equivalent_to_system_defaults

PROMETHEUS_JOB = "clean-custom-staleness"
LOGGER_NAME = "clean_custom_staleness"
COLLECTED_METRICS: tuple = ()
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"

SYSTEM_DEFAULTS = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
}


def run(
    logger: Logger,
    session: Session,
    application: FlaskApp,
) -> None:
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    with application.app.app_context():
        threadctx.request_id = None

        staleness_query = session.query(Staleness)
        total = staleness_query.count()
        logger.info("Inspecting %d custom staleness row(s).", total)

        to_delete = []
        for row in staleness_query.yield_per(1000):
            row_dict = {
                "conventional_time_to_stale": row.conventional_time_to_stale,
                "conventional_time_to_stale_warning": row.conventional_time_to_stale_warning,
                "conventional_time_to_delete": row.conventional_time_to_delete,
            }
            if staleness_equivalent_to_system_defaults(row_dict, sys_defaults=SYSTEM_DEFAULTS):
                logger.info(
                    "org_id=%s is equivalent to system defaults (stale=%d, warning=%d, delete=%d) — %s",
                    row.org_id,
                    row.conventional_time_to_stale,
                    row.conventional_time_to_stale_warning,
                    row.conventional_time_to_delete,
                    "would delete" if dry_run else "will delete",
                )
                to_delete.append(row)
            else:
                logger.debug(
                    "org_id=%s has custom staleness — retaining (stale=%d, warning=%d, delete=%d)",
                    row.org_id,
                    row.conventional_time_to_stale,
                    row.conventional_time_to_stale_warning,
                    row.conventional_time_to_delete,
                )

        retained = total - len(to_delete)
        logger.info(
            "Summary: inspected=%d, to_delete=%d, to_retain=%d",
            total,
            len(to_delete),
            retained,
        )

        if dry_run:
            logger.info("DRY_RUN is enabled; no changes written.")
            return

        deleted = 0
        deleted_org_ids = []
        with session_guard(session, close=False):
            for row in to_delete:
                org_id = row.org_id
                session.delete(row)
                deleted += 1
                deleted_org_ids.append(org_id)
                logger.info("Deleted staleness row for org_id=%s", org_id)

        # Invalidate caches after the transaction has been committed.
        for org_id in deleted_org_ids:
            try:
                StalenessCache.delete(org_id)
                logger.info("Invalidated staleness cache for org_id=%s", org_id)
            except Exception:
                logger.exception("Failed to invalidate cache for org_id=%s (DB delete succeeded)", org_id)

        logger.info("Finished. Deleted %d row(s), retained %d row(s).", deleted, retained)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    if SUSPEND_JOB:
        logger.info(
            "SUSPEND_JOB is true; exiting without action. To enable this job, set SUSPEND_JOB=false and DRY_RUN=false."
        )
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
