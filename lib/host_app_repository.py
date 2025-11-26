from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.logging import get_logger
from app.models import db

logger = get_logger(__name__)

__all__ = ("upsert_host_app_data",)


def upsert_host_app_data(
    model_class: type,
    application: str,
    org_id: str,
    hosts_data: list[dict[str, Any]],
) -> int:
    """
    Perform efficient upsert (INSERT ... ON CONFLICT DO UPDATE) for host application data.

    This function inserts new records or updates existing ones based on the composite
    primary key (org_id, host_id). All application-specific columns are updated on conflict.

    Args:
        model_class: SQLAlchemy model class (e.g., HostAppDataAdvisor)
        application: Application name for logging (e.g., "advisor", "vulnerability")
        org_id: Organization ID
        hosts_data: List of dictionaries containing host data to upsert.
                    Each dict should include: org_id, host_id, last_updated, and app-specific fields

    Returns:
        Number of hosts successfully upserted
    """
    if not hosts_data:
        logger.info(f"No hosts to upsert for {application}", extra={"application": application, "org_id": org_id})
        return 0

    # Create INSERT statement with all host data
    stmt = insert(model_class).values(hosts_data)

    # Create update dictionary excluding primary key columns (org_id, host_id)
    # On conflict, update all other columns with the new values
    update_dict = {col: stmt.excluded[col] for col in hosts_data[0].keys() if col not in ["org_id", "host_id"]}

    # Add ON CONFLICT clause to perform upsert
    stmt = stmt.on_conflict_do_update(
        index_elements=["org_id", "host_id"],
        set_=update_dict,
    )

    # Execute the statement
    db.session.execute(stmt)
    db.session.flush()

    success_count = len(hosts_data)
    logger.info(
        f"Successfully upserted {success_count} host records for {application}",
        extra={
            "application": application,
            "org_id": org_id,
            "success_count": success_count,
        },
    )

    return success_count
