from sqlalchemy.orm.exc import NoResultFound

from app.logging import get_logger
from app.models import Staleness
from app.staleness_serialization import build_serialized_acc_staleness_obj
from app.staleness_serialization import build_staleness_sys_default

logger = get_logger(__name__)


def get_staleness_obj(org_id):
    try:
        staleness = Staleness.query.filter(Staleness.org_id == org_id).one()
        logger.info("Using custom account staleness")
        staleness = build_serialized_acc_staleness_obj(staleness)
    except NoResultFound:
        logger.debug(f"No data found for user {org_id}, using system default values")
        staleness = build_staleness_sys_default(org_id)
        return staleness

    return staleness
