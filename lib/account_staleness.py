from app.auth import get_current_identity
from app.logging import get_logger
from app.models import AccountStalenessCulling
from app.models import db
from lib.db import session_guard

logger = get_logger(__name__)


def add_account_staleness(account_staleness_data) -> AccountStalenessCulling:
    logger.debug("Creating a new AccountStaleness: %s", account_staleness_data)
    conventional_staleness_delta = account_staleness_data.get("conventional_staleness_delta")
    conventional_stale_warning_delta = account_staleness_data.get("conventional_stale_warning_delta")
    conventional_culling_delta = account_staleness_data.get("conventional_culling_delta")
    immutable_staleness_delta = account_staleness_data.get("immutable_staleness_delta")
    immutable_stale_warning_delta = account_staleness_data.get("immutable_stale_warning_delta")
    immutable_culling_delta = account_staleness_data.get("immutable_culling_delta")
    org_id = get_current_identity().org_id
    account = get_current_identity().account_number

    with session_guard(db.session):
        new_staleness = AccountStalenessCulling(
            org_id=org_id,
            account=account,
            conventional_staleness_delta=conventional_staleness_delta,
            conventional_stale_warning_delta=conventional_stale_warning_delta,
            conventional_culling_delta=conventional_culling_delta,
            immutable_staleness_delta=immutable_staleness_delta,
            immutable_stale_warning_delta=immutable_stale_warning_delta,
            immutable_culling_delta=immutable_culling_delta,
        )
        db.session.add(new_staleness)
        db.session.flush()

    # gets the AccountStalenessCulling object after it has been committed
    created_staleness = AccountStalenessCulling.query.filter(AccountStalenessCulling.org_id == org_id).one_or_none()

    return created_staleness


def patch_account_staleness(account_staleness_data) -> AccountStalenessCulling:
    logger.debug("Updating AccountStaleness: %s", account_staleness_data)
    org_id = get_current_identity().org_id

    updated_data = {key: value for (key, value) in account_staleness_data.items() if value}

    AccountStalenessCulling.query.filter(AccountStalenessCulling.org_id == org_id).update(updated_data)
    db.session.commit()

    updated_staleness = AccountStalenessCulling.query.filter(AccountStalenessCulling.org_id == org_id).one_or_none()

    return updated_staleness


def remove_account_staleness() -> None:
    org_id = get_current_identity().org_id

    logger.debug("Removing AccountStaleness for org_id: %s", org_id)
    staleness = AccountStalenessCulling.query.filter(AccountStalenessCulling.org_id == org_id).one()
    db.session.delete(staleness)
    db.session.commit()
