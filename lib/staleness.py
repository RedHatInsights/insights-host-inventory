from app.auth import get_current_identity
from app.auth.identity import Identity
from app.logging import get_logger
from app.models import Staleness
from app.models import db
from lib.db import session_guard

logger = get_logger(__name__)

# If every conventional field differs from system defaults by **strictly less** than
# this many seconds, treat the payload as "default" and do not keep a custom row.
# A difference of exactly this many seconds (e.g. one hour) is not equivalent.
DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS = 60 * 60

_STALENESS_CONVENTIONAL_KEYS = (
    "conventional_time_to_stale",
    "conventional_time_to_stale_warning",
    "conventional_time_to_delete",
)


def staleness_equivalent_to_system_defaults(staleness_data: dict, identity: Identity) -> bool:
    """Return True if every conventional field is **strictly less than** one hour from system defaults.

    Differences of exactly 3600 seconds (one hour) or more for any field are not
    considered equivalent. API validation merges PATCH/POST with the org view so
    :class:`StalenessSchema` supplies all three keys. If a key is missing or not
    an int, treat the payload as not equivalent to defaults.
    """
    from app.staleness_serialization import get_sys_default_staleness_api

    default = get_sys_default_staleness_api(identity)
    for k in _STALENESS_CONVENTIONAL_KEYS:
        v = staleness_data.get(k)
        if v is None or not isinstance(v, int):
            return False
        if abs(v - default[k]) >= DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS:
            return False
    return True


def org_has_custom_staleness(org_id: str) -> bool:
    return Staleness.query.filter_by(org_id=org_id).first() is not None


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
