from datetime import datetime
from datetime import timezone

from flask import g
from sqlalchemy.orm.exc import NoResultFound

from app.auth import get_current_identity
from app.logging import get_logger
from app.models import AccountStalenessCulling


logger = get_logger(__name__)


def get_account_staleness_db(rbac_filter=None, identity=None):
    # TODO: ESSNTL-5163
    if rbac_filter:
        pass

    """
        Uses flask g to store account staleness data
        so it is made only 1 call to the DB.
        This is useful in the hosts serialization,
        specially when a list of hosts are fetched
    """
    if "acc_st" in g:
        return g.acc_st
    else:
        logger.debug("Account staleness data is not available in global request context")
        if not identity:
            org_id = get_current_identity().org_id
            account = get_current_identity().account_number
        else:
            org_id = identity.org_id
            account = identity.account_number
        try:
            filters = (AccountStalenessCulling.org_id == org_id,)
            acc_st = AccountStalenessCulling.query.filter(*filters).one()
            logger.info("Using custom account staleness")
            logger.debug("Setting account staleness data to global request context")
            g.acc_st = _build_serialized_acc_staleness_obj(acc_st)
        except NoResultFound:
            logger.info(f"No data found for user {org_id}, using system default values")
            acc_st = _build_acc_staleness_sys_default(org_id, account)
            logger.debug("Setting account staleness data to global request context")
            g.acc_st = acc_st
            return g.acc_st

        return g.acc_st


def _build_acc_staleness_sys_default(org_id, account):
    from app import inventory_config

    config = inventory_config()
    return AttrDict(
        {
            "id": "system_default",
            "account": account,
            "org_id": org_id,
            "conventional_staleness_delta": config.conventional_staleness_seconds,
            "conventional_stale_warning_delta": config.conventional_stale_warning_seconds,
            "conventional_culling_delta": config.conventional_culling_seconds,
            "immutable_staleness_delta": config.immutable_staleness_seconds,
            "immutable_stale_warning_delta": config.immutable_stale_warning_seconds,
            "immutable_culling_delta": config.immutable_culling_seconds,
            "created_on": datetime.now(timezone.utc),
            "modified_on": datetime.now(timezone.utc),
        }
    )


# This is required because we do not keep a ORM object that is attached to a session
# leaving in the global scope. Before this serialization,
# it was causing sqlalchemy.orm.exc.DetachedInstanceError
def _build_serialized_acc_staleness_obj(acc_st):
    return AttrDict(
        {
            "id": str(acc_st.id),
            "account": acc_st.account,
            "org_id": acc_st.org_id,
            "conventional_staleness_delta": acc_st.conventional_staleness_delta,
            "conventional_stale_warning_delta": acc_st.conventional_stale_warning_delta,
            "conventional_culling_delta": acc_st.conventional_culling_delta,
            "immutable_staleness_delta": acc_st.immutable_staleness_delta,
            "immutable_stale_warning_delta": acc_st.immutable_stale_warning_delta,
            "immutable_culling_delta": acc_st.immutable_culling_delta,
            "created_on": acc_st.created_on,
            "modified_on": acc_st.modified_on,
        }
    )


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
