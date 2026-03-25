from sqlalchemy.orm.exc import NoResultFound

from app.logging import get_logger
from app.models import Staleness
from app.models import db
from app.models.utils import StalenessCache
from app.staleness_serialization import AttrDict
from app.staleness_serialization import build_serialized_acc_staleness_obj
from app.staleness_serialization import build_staleness_sys_default

logger = get_logger(__name__)


def get_staleness_obj(org_id: str) -> AttrDict:
    cached = StalenessCache.get(org_id)
    if cached is not None:
        return cached

    try:
        staleness = db.session.query(Staleness).filter(Staleness.org_id == org_id).one()
        logger.info(f"Using custom staleness for org {org_id}.")
        staleness = build_serialized_acc_staleness_obj(staleness)
    except NoResultFound:
        logger.debug(f"No custom staleness data found for org {org_id}, using system default values instead.")
        staleness = build_staleness_sys_default(org_id)

    StalenessCache.put(org_id, staleness)
    return staleness
