from __future__ import annotations

from typing import Any

from psycopg2.errors import ForeignKeyViolation
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.logging import get_logger
from app.models import db

logger = get_logger(__name__)

__all__ = ("upsert_host_app_data",)


def _build_upsert_stmt(model_class: type, rows: list[dict[str, Any]]):
    stmt = insert(model_class).values(rows)
    update_cols = {col: stmt.excluded[col] for col in rows[0] if col not in ("org_id", "host_id")}
    return stmt.on_conflict_do_update(index_elements=["org_id", "host_id"], set_=update_cols)


def _upsert_individually(
    model_class: type,
    application: str,
    org_id: str,
    hosts_data: list[dict[str, Any]],
) -> int:
    """Fallback: upsert one row at a time using savepoints so a single
    deleted host doesn't prevent the rest of the batch from being persisted."""
    success_count = 0
    for row in hosts_data:
        try:
            with db.session.begin_nested():
                db.session.execute(_build_upsert_stmt(model_class, [row]))
            success_count += 1
        except IntegrityError as e:
            if not isinstance(e.orig, ForeignKeyViolation):
                raise
            logger.warning(
                "Host %s no longer exists, skipping %s app data upsert",
                row.get("host_id"),
                application,
                extra={"application": application, "org_id": org_id, "host_id": str(row.get("host_id"))},
            )
    return success_count


def upsert_host_app_data(
    model_class: type,
    application: str,
    org_id: str,
    hosts_data: list[dict[str, Any]],
) -> int:
    """
    Perform efficient upsert (INSERT ... ON CONFLICT DO UPDATE) for host application data.

    If a FK violation occurs (host deleted between ingestion and upsert), the batch
    is retried row-by-row so that valid hosts are still persisted.

    Returns:
        Number of hosts successfully upserted
    """
    if not hosts_data:
        logger.info(f"No hosts to upsert for {application}", extra={"application": application, "org_id": org_id})
        return 0

    try:
        with db.session.begin_nested():
            db.session.execute(_build_upsert_stmt(model_class, hosts_data))
        success_count = len(hosts_data)
    except IntegrityError as e:
        if not isinstance(e.orig, ForeignKeyViolation):
            raise
        success_count = _upsert_individually(model_class, application, org_id, hosts_data)

    logger.info(
        f"Successfully upserted {success_count} host records for {application}",
        extra={"application": application, "org_id": org_id, "success_count": success_count},
    )
    return success_count
