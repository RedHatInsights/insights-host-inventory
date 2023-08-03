from sqlalchemy.orm.exc import NoResultFound

from app.auth import get_current_identity
from app.culling import build_acc_staleness_sys_default
from app.logging import get_logger
from app.models import AccountStalenessCulling


logger = get_logger(__name__)


def get_account_staleness_db(rbac_filter=None):
    # TODO: ESSNTL-5163
    if rbac_filter:
        pass

    try:
        org_id = get_current_identity().org_id
        account = get_current_identity().account_number
        filters = (AccountStalenessCulling.org_id == org_id,)
        acc_st = AccountStalenessCulling.query.filter(*filters).one()
    except NoResultFound:
        logger.info(f"No data found for user {org_id}, using system default values")
    finally:
        acc_st = build_acc_staleness_sys_default(org_id, account)

    return acc_st
