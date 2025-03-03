from sqlalchemy.orm.exc import NoResultFound

from app.auth import get_current_identity
from app.logging import get_logger
from app.models import Staleness
from app.staleness_serialization import build_serialized_acc_staleness_obj
from app.staleness_serialization import build_staleness_sys_default

logger = get_logger(__name__)


def get_staleness_obj(identity=None):
    org_id = get_current_identity().org_id if not identity else identity.org_id
    try:
        staleness = Staleness.query.filter(Staleness.org_id == org_id).one()
        logger.info("Using custom account staleness")
        staleness = build_serialized_acc_staleness_obj(staleness)
    except NoResultFound:
        logger.debug(f"No data found for user {org_id}, using system default values")
        staleness = build_staleness_sys_default(org_id)
        return staleness

    return staleness


def get_sys_default_staleness(config=None):
    return build_staleness_sys_default("000000", config)


def get_sys_default_staleness_api(identity, config=None):
    org_id = identity.org_id or "00000"
    return build_staleness_sys_default(org_id, config)
