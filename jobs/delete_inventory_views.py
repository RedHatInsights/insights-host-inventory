#!/usr/bin/env python3
"""
Job to delete specific saved views (``inventory_views``) by ID.

Used to remove legacy/malformed views -- e.g. views whose stored advisor/
vulnerability host filters predate the current enum-array schema and make the
whole ``GET /views`` list fail response validation (``Response body does not
conform to specification``) and return 500. Triggered via ClowdJobInvocation
(CJI).

Deleting a view also cascades to any ``user_view_preferences`` row whose
``default_view_id`` references it (FK ``ON DELETE CASCADE``); the count is
reported before the delete.

Environment variables:
    VIEW_IDS          - (required) Comma-separated list of view UUIDs to delete
    DRY_RUN=true      - Log what would be deleted without writing (default: true)
    SUSPEND_JOB=true  - Exit immediately as a safety gate (default: true)
"""

from __future__ import annotations

import os
import sys
import uuid
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.logging import threadctx
from app.models import InventoryView
from app.models import UserViewPreference
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "delete-inventory-views"
LOGGER_NAME = "delete_inventory_views"
COLLECTED_METRICS: tuple = ()
MAX_VIEW_IDS_LOGGED = 20


def _env_flag(name: str, default: bool = True) -> bool:
    """Read a boolean environment variable (\"true\"/\"false\", case-insensitive)."""
    default_str = "true" if default else "false"
    return os.environ.get(name, default_str).lower() == "true"


SUSPEND_JOB = _env_flag("SUSPEND_JOB", default=True)


def _parse_view_ids(raw: str) -> list[str]:
    """Split a comma-separated VIEW_IDS string into a de-duplicated ordered list."""
    seen: set[str] = set()
    view_ids: list[str] = []
    for part in raw.split(","):
        view_id = part.strip()
        if not view_id or view_id in seen:
            continue
        seen.add(view_id)
        view_ids.append(view_id)
    return view_ids


def _validate_uuids(view_ids: list[str], logger: Logger) -> list[uuid.UUID]:
    """Return the parseable UUIDs, warning on and skipping any malformed value."""
    valid: list[uuid.UUID] = []
    for view_id in view_ids:
        try:
            valid.append(uuid.UUID(view_id))
        except ValueError:
            logger.warning("Skipping invalid view UUID: %s", view_id)
    return valid


def _format_ids_for_log(ids: list[str]) -> list[str]:
    """Return IDs for logging, truncating when the list is long."""
    if len(ids) <= MAX_VIEW_IDS_LOGGED:
        return ids
    remaining = len(ids) - MAX_VIEW_IDS_LOGGED
    return [*ids[:MAX_VIEW_IDS_LOGGED], f"...and {remaining} more"]


def run(logger: Logger, session: Session, application: FlaskApp) -> None:
    raw_view_ids = os.environ.get("VIEW_IDS", "").strip()
    if not raw_view_ids:
        logger.error("VIEW_IDS is required but not set or empty.")
        sys.exit(1)

    requested = _validate_uuids(_parse_view_ids(raw_view_ids), logger)
    if not requested:
        logger.error("VIEW_IDS contained no valid view UUIDs.")
        sys.exit(1)

    dry_run = _env_flag("DRY_RUN", default=True)

    with application.app.app_context():
        threadctx.request_id = None

        existing = [vid for (vid,) in session.query(InventoryView.id).filter(InventoryView.id.in_(requested)).all()]
        existing_str = sorted(str(vid) for vid in existing)

        missing = sorted(str(vid) for vid in requested if vid not in set(existing))
        if missing:
            logger.warning("View id(s) not found (skipping): %s", _format_ids_for_log(missing))

        if not existing:
            logger.info("No matching views to delete.")
            return

        pref_refs = session.query(UserViewPreference).filter(UserViewPreference.default_view_id.in_(existing)).count()

        logger.info("Will delete %d view(s): %s", len(existing), _format_ids_for_log(existing_str))
        if pref_refs:
            logger.info("This will also cascade-delete %d user_view_preference row(s).", pref_refs)

        if dry_run:
            logger.info("DRY_RUN is enabled; no changes written.")
            return

        with session_guard(session, close=False):
            result = session.execute(delete(InventoryView).where(InventoryView.id.in_(existing)))
            total_deleted = result.rowcount

        logger.info("Finished deleting views. Total deleted: %d", total_deleted)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    job_type = "Delete inventory views"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup(COLLECTED_METRICS, PROMETHEUS_JOB)

    try:
        run(logger, session, application)
    except Exception as e:
        logger.exception("Job failed: %s", e)
        sys.exit(1)
    finally:
        session.close()
