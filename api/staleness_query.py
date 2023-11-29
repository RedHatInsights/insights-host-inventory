from sqlalchemy.orm.exc import NoResultFound

from app.auth import get_current_identity
from app.logging import get_logger
from app.models import Staleness


logger = get_logger(__name__)


def get_staleness_obj(identity=None):
    if not identity:
        org_id = get_current_identity().org_id
    else:
        org_id = identity.org_id
    try:
        filters = (Staleness.org_id == org_id,)
        acc_st = Staleness.query.filter(*filters).one()
        logger.info("Using custom account staleness")
        logger.debug("Setting account staleness data to global request context")
        acc_st = _build_serialized_acc_staleness_obj(acc_st)
    except NoResultFound:
        logger.info(f"No data found for user {org_id}, using system default values")
        acc_st = _build_staleness_sys_default(org_id)
        return acc_st

    return acc_st


def get_sys_default_staleness(config=None):
    org_id = "000000"
    acc_st = _build_staleness_sys_default(org_id, config)
    return acc_st


def _build_staleness_sys_default(org_id, config=None):
    if not config:
        from app import inventory_config

        config = inventory_config()

    return AttrDict(
        {
            "id": "system_default",
            "org_id": org_id,
            "conventional_staleness_delta": config.conventional_staleness_seconds,
            "conventional_stale_warning_delta": config.conventional_stale_warning_seconds,
            "conventional_culling_delta": config.conventional_culling_seconds,
            "immutable_staleness_delta": config.immutable_staleness_seconds,
            "immutable_stale_warning_delta": config.immutable_stale_warning_seconds,
            "immutable_culling_delta": config.immutable_culling_seconds,
            "created_on": "N/A",
            "modified_on": "N/A",
        }
    )


# This is required because we do not keep a ORM object that is attached to a session
# leaving in the global scope. Before this serialization,
# it was causing sqlalchemy.orm.exc.DetachedInstanceError
def _build_serialized_acc_staleness_obj(acc_st):
    return AttrDict(
        {
            "id": str(acc_st.id),
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
