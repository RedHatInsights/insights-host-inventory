from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg2.errors import ForeignKeyViolation
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.logging import get_logger
from app.models import db

logger = get_logger(__name__)

__all__ = ("upsert_host_app_data",)


def _build_upsert_stmt(model_class: type, rows: list[dict[str, Any]]):
    stmt = insert(model_class).values(rows)
    update_cols = {col: stmt.excluded[col] for col in rows[0] if col not in ("org_id", "host_id")}
    return stmt.on_conflict_do_update(
        index_elements=["org_id", "host_id"],
        set_=update_cols,
        where=or_(*(stmt.table.c[col].is_distinct_from(stmt.excluded[col]) for col in update_cols)),
    ).returning(stmt.table.c.host_id)


def _upsert_individually(
    model_class: type,
    application: str,
    org_id: str,
    hosts_data: list[dict[str, Any]],
    changed_ids: list[UUID],
) -> list[UUID]:
    """Fallback: upsert one row at a time using savepoints so a single
    deleted host doesn't prevent the rest of the batch from being persisted."""
    successful_ids: list[UUID] = []
    for row in hosts_data:
        try:
            with db.session.begin_nested():
                changed = db.session.execute(_build_upsert_stmt(model_class, [row])).scalars().all()
            successful_ids.append(UUID(str(row["host_id"])))
            changed_ids.extend(changed)
        except IntegrityError as e:
            if not isinstance(e.orig, ForeignKeyViolation):
                raise
            logger.warning(
                "Host %s no longer exists, skipping %s app data upsert",
                row.get("host_id"),
                application,
                extra={"application": application, "org_id": org_id, "host_id": str(row.get("host_id"))},
            )
    return successful_ids


def upsert_host_app_data(
    model_class: type,
    application: str,
    org_id: str,
    hosts_data: list[dict[str, Any]],
    *,
    changed_ids: list[UUID] | None = None,
) -> list[UUID]:
    """
    Perform efficient upsert (INSERT ... ON CONFLICT DO UPDATE) for host application data.

    If a FK violation occurs (host deleted between ingestion and upsert), the batch
    is retried row-by-row so that valid hosts are still persisted.

    Returns:
        UUIDs of successfully processed hosts (including exact replays), excluding FK skips.
        If supplied, changed_ids receives only rows changed by this transaction.
    """
    if not hosts_data:
        logger.info(f"No hosts to upsert for {application}", extra={"application": application, "org_id": org_id})
        return []

    changed: list[UUID] = []
    try:
        with db.session.begin_nested():
            changed = list(db.session.execute(_build_upsert_stmt(model_class, hosts_data)).scalars())
        successful_ids = [UUID(str(row["host_id"])) for row in hosts_data]
    except IntegrityError as e:
        if not isinstance(e.orig, ForeignKeyViolation):
            raise
        changed = []
        successful_ids = _upsert_individually(model_class, application, org_id, hosts_data, changed)

    if changed_ids is not None:
        changed_ids.extend(changed)

    success_count = len(successful_ids)
    logger.info(
        f"Successfully upserted {success_count} host records for {application}",
        extra={"application": application, "org_id": org_id, "success_count": success_count},
    )
    return successful_ids
