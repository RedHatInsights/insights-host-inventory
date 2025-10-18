from app.auth import get_current_identity
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.logging import get_logger
from app.models import Staleness
from app.models import db
from lib.db import session_guard

logger = get_logger(__name__)

# Tolerance for considering custom staleness values "close enough" to defaults
# If all custom values are within this tolerance of defaults, the custom staleness will be removed
STALENESS_DEFAULT_TOLERANCE_SECONDS = 60


def _is_close_to_default(value: int, default: int, tolerance: int = STALENESS_DEFAULT_TOLERANCE_SECONDS) -> bool:
    """Check if a value is within tolerance of the default value."""
    return abs(value - default) <= tolerance


def _should_remove_custom_staleness(staleness_data: dict) -> bool:
    """
    Check if all custom staleness values are close enough to defaults to warrant removal.

    Returns True if all provided staleness values are within tolerance of their defaults,
    indicating that the custom staleness configuration should be removed.
    """
    conventional_time_to_stale = staleness_data.get("conventional_time_to_stale")
    conventional_time_to_stale_warning = staleness_data.get("conventional_time_to_stale_warning")
    conventional_time_to_delete = staleness_data.get("conventional_time_to_delete")

    # Check each value that's provided
    checks = []

    if conventional_time_to_stale is not None:
        checks.append(_is_close_to_default(conventional_time_to_stale, CONVENTIONAL_TIME_TO_STALE_SECONDS))

    if conventional_time_to_stale_warning is not None:
        checks.append(
            _is_close_to_default(conventional_time_to_stale_warning, CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
        )

    if conventional_time_to_delete is not None:
        checks.append(_is_close_to_default(conventional_time_to_delete, CONVENTIONAL_TIME_TO_DELETE_SECONDS))

    # Only return True if all checks passed (all values are close to defaults)
    return len(checks) > 0 and all(checks)


def add_staleness(staleness_data) -> Staleness | None:
    logger.debug("Creating a new AccountStaleness: %s", staleness_data)
    org_id = get_current_identity().org_id

    # Check if the values are close enough to defaults to not bother creating custom staleness
    if _should_remove_custom_staleness(staleness_data):
        logger.info(
            f"Requested staleness values for org_id {org_id} are within tolerance of defaults. "
            "Not creating custom staleness configuration."
        )
        # Return None to indicate that custom staleness was not created (caller should use defaults)
        return None

    conventional_time_to_stale = staleness_data.get("conventional_time_to_stale")
    conventional_time_to_stale_warning = staleness_data.get("conventional_time_to_stale_warning")
    conventional_time_to_delete = staleness_data.get("conventional_time_to_delete")

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


def patch_staleness(staleness_data) -> Staleness | None:
    logger.debug("Updating AccountStaleness: %s", staleness_data)
    org_id = get_current_identity().org_id

    # Check if the updated values are close enough to defaults to remove custom staleness
    if _should_remove_custom_staleness(staleness_data):
        logger.info(
            f"Custom staleness values for org_id {org_id} are within tolerance of defaults. "
            "Removing custom staleness configuration."
        )
        remove_staleness()
        # Return None to indicate that custom staleness was removed (caller should use defaults)
        return None

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
