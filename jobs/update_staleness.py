#!/usr/bin/env python3
"""
Job to create or update a custom staleness row for a given org_id.

Devs cannot directly modify Prod DB rows, and the existing staleness API
requires authentication as the target org.  This CJI-triggered job allows
SREs to set custom staleness values for any org_id via environment variables.

Environment variables:
    STALENESS_ORG_ID          - (required) The org_id to upsert staleness for
    CONVENTIONAL_TIME_TO_STALE         - Seconds (optional; defaults to existing or system default)
    CONVENTIONAL_TIME_TO_STALE_WARNING - Seconds (optional; defaults to existing or system default)
    CONVENTIONAL_TIME_TO_DELETE        - Seconds (optional; defaults to existing or system default)
    DRY_RUN=true      - Log what would change without writing (default: true)
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
from app.models.schemas.staleness import StalenessSchema
from app.models.utils import StalenessCache
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "update-staleness"
LOGGER_NAME = "update_staleness"
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


def _read_env_staleness_values(logger: Logger) -> dict[str, int]:
    """Read optional staleness env vars and return only those that are set.
    At least one of these staleness env vars must be set.
    """
    env_mapping = {
        "conventional_time_to_stale": "CONVENTIONAL_TIME_TO_STALE",
        "conventional_time_to_stale_warning": "CONVENTIONAL_TIME_TO_STALE_WARNING",
        "conventional_time_to_delete": "CONVENTIONAL_TIME_TO_DELETE",
    }
    values: dict[str, int] = {}
    for field, env_var in env_mapping.items():
        raw = os.environ.get(env_var)
        if raw is not None:
            try:
                values[field] = int(raw)
            except ValueError:
                logger.error("%s must be an integer, got: %r", env_var, raw)
                sys.exit(1)
    return values


def _merge_with_defaults(
    explicit: dict[str, int],
    existing_row: Staleness | None,
) -> dict[str, int]:
    """Fill in any missing fields from the existing row or system defaults."""
    merged: dict[str, int] = {}
    for field in STALENESS_FIELDS:
        if field in explicit:
            merged[field] = explicit[field]
        elif existing_row is not None:
            merged[field] = getattr(existing_row, field)
        else:
            merged[field] = SYSTEM_DEFAULTS[field]
    return merged


def run(
    logger: Logger,
    session: Session,
    application: FlaskApp,
) -> None:
    org_id = os.environ.get("STALENESS_ORG_ID", "").strip()
    if not org_id:
        logger.error("STALENESS_ORG_ID is required but not set or empty.")
        sys.exit(1)

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    explicit_values = _read_env_staleness_values(logger)
    if not explicit_values:
        logger.error("At least one CONVENTIONAL_TIME_TO_* env var must be set.")
        sys.exit(1)

    with application.app.app_context():
        threadctx.request_id = None

        existing_row = session.query(Staleness).filter(Staleness.org_id == org_id).one_or_none()
        merged = _merge_with_defaults(explicit_values, existing_row)

        errors = StalenessSchema().validate(merged)
        if errors:
            logger.error("Validation failed: %s", errors)
            sys.exit(1)

        action = "update" if existing_row else "create"
        logger.info(
            "Will %s staleness for org_id=%s: stale=%d, warning=%d, delete=%d",
            action,
            org_id,
            merged["conventional_time_to_stale"],
            merged["conventional_time_to_stale_warning"],
            merged["conventional_time_to_delete"],
        )

        if dry_run:
            logger.info("DRY_RUN is enabled; no changes written.")
            return

        if existing_row:
            with session_guard(session, close=False):
                for field in STALENESS_FIELDS:
                    setattr(existing_row, field, merged[field])
            logger.info("Updated staleness row for org_id=%s", org_id)
        else:
            with session_guard(session, close=False):
                new_row = Staleness(
                    org_id=org_id,
                    conventional_time_to_stale=merged["conventional_time_to_stale"],
                    conventional_time_to_stale_warning=merged["conventional_time_to_stale_warning"],
                    conventional_time_to_delete=merged["conventional_time_to_delete"],
                )
                session.add(new_row)
            logger.info("Created staleness row for org_id=%s", org_id)

        StalenessCache.delete(org_id)
        logger.info("Invalidated staleness cache for org_id=%s", org_id)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    job_type = "Update staleness"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup(COLLECTED_METRICS, PROMETHEUS_JOB)

    try:
        run(logger, session, application)
    except Exception as e:
        logger.exception("Job failed: %s", e)
        sys.exit(1)
    finally:
        session.close()
