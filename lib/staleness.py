from app.auth import get_current_identity
from app.logging import get_logger
from app.models import Staleness
from app.models import db
from lib.db import session_guard

logger = get_logger(__name__)


def add_staleness(staleness_data) -> Staleness:
    logger.debug("Creating a new AccountStaleness: %s", staleness_data)
    conventional_time_to_stale = staleness_data.get("conventional_time_to_stale")
    conventional_time_to_stale_warning = staleness_data.get("conventional_time_to_stale_warning")
    conventional_time_to_delete = staleness_data.get("conventional_time_to_delete")
    immutable_time_to_stale = staleness_data.get("immutable_time_to_stale")
    immutable_time_to_stale_warning = staleness_data.get("immutable_time_to_stale_warning")
    immutable_time_to_delete = staleness_data.get("immutable_time_to_delete")
    org_id = get_current_identity().org_id

    with session_guard(db.session):
        new_staleness = Staleness(
            org_id=org_id,
            conventional_time_to_stale=conventional_time_to_stale,
            conventional_time_to_stale_warning=conventional_time_to_stale_warning,
            conventional_time_to_delete=conventional_time_to_delete,
            immutable_time_to_stale=immutable_time_to_stale,
            immutable_time_to_stale_warning=immutable_time_to_stale_warning,
            immutable_time_to_delete=immutable_time_to_delete,
        )
        db.session.add(new_staleness)
        db.session.flush()

    # gets the Staleness object after it has been committed
    created_staleness = Staleness.query.filter(Staleness.org_id == org_id).one_or_none()

    return created_staleness


def patch_staleness(staleness_data) -> Staleness:
    logger.debug("Updating AccountStaleness: %s", staleness_data)
    org_id = get_current_identity().org_id

    updated_data = {key: value for (key, value) in staleness_data.items() if value}

    Staleness.query.filter(Staleness.org_id == org_id).update(updated_data)
    db.session.commit()

    updated_staleness = Staleness.query.filter(Staleness.org_id == org_id).one_or_none()

    return updated_staleness


def remove_staleness() -> None:
    org_id = get_current_identity().org_id

    logger.debug("Removing AccountStaleness for org_id: %s", org_id)
    staleness = Staleness.query.filter(Staleness.org_id == org_id).one()
    db.session.delete(staleness)
    db.session.commit()
