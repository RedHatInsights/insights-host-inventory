from app.auth import get_current_identity
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.logging import get_logger
from app.models import Staleness
from app.models import db
from lib.db import session_guard

logger = get_logger(__name__)

# Records whose values are within this many seconds of the system defaults are
# considered effectively identical to the defaults and should not be stored.
NEAR_DEFAULT_THRESHOLD_SECONDS = 3600  # 1 hour


def is_staleness_near_default(staleness) -> bool:
    """Return True if all staleness values are within NEAR_DEFAULT_THRESHOLD_SECONDS of the system defaults.

    Accepts either a dict (for incoming API data) or a Staleness model object.
    """
    if isinstance(staleness, dict):
        stale = staleness.get("conventional_time_to_stale", CONVENTIONAL_TIME_TO_STALE_SECONDS)
        warning = staleness.get("conventional_time_to_stale_warning", CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
        delete = staleness.get("conventional_time_to_delete", CONVENTIONAL_TIME_TO_DELETE_SECONDS)
    else:
        stale = staleness.conventional_time_to_stale
        warning = staleness.conventional_time_to_stale_warning
        delete = staleness.conventional_time_to_delete

    return (
        abs(stale - CONVENTIONAL_TIME_TO_STALE_SECONDS) <= NEAR_DEFAULT_THRESHOLD_SECONDS
        and abs(warning - CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS) <= NEAR_DEFAULT_THRESHOLD_SECONDS
        and abs(delete - CONVENTIONAL_TIME_TO_DELETE_SECONDS) <= NEAR_DEFAULT_THRESHOLD_SECONDS
    )


def add_staleness(staleness_data) -> Staleness:
    logger.debug("Creating a new AccountStaleness: %s", staleness_data)
    conventional_time_to_stale = staleness_data.get("conventional_time_to_stale")
    conventional_time_to_stale_warning = staleness_data.get("conventional_time_to_stale_warning")
    conventional_time_to_delete = staleness_data.get("conventional_time_to_delete")
    org_id = get_current_identity().org_id

    with session_guard(db.session):
        new_staleness = Staleness(
            org_id=org_id,
            conventional_time_to_stale=conventional_time_to_stale,
            conventional_time_to_stale_warning=conventional_time_to_stale_warning,
            conventional_time_to_delete=conventional_time_to_delete,
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


def remove_staleness_if_exists() -> bool:
    """Delete the custom staleness record for the current org if one exists.

    Returns True if a record was deleted, False if no record existed.
    """
    org_id = get_current_identity().org_id
    staleness = Staleness.query.filter(Staleness.org_id == org_id).one_or_none()
    if staleness is None:
        return False
    logger.debug("Removing near-default AccountStaleness for org_id: %s", org_id)
    db.session.delete(staleness)
    db.session.commit()
    return True
