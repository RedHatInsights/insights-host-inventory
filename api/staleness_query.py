from sqlalchemy.orm.exc import NoResultFound

from app.auth import get_current_identity
from app.common import inventory_config
from app.logging import get_logger
from app.models import Staleness


logger = get_logger(__name__)


def get_staleness_obj(identity=None):
    if not identity:
        org_id = get_current_identity().org_id
    else:
        org_id = identity.org_id
    try:
        staleness = Staleness.query.filter(Staleness.org_id == org_id).one()
        logger.info("Using custom account staleness")
        staleness = _build_serialized_acc_staleness_obj(staleness)
    except NoResultFound:
        logger.info(f"No data found for user {org_id}, using system default values")
        staleness = _build_staleness_sys_default(org_id)
        return staleness

    return staleness


def get_sys_default_staleness(config=None):
    return _build_staleness_sys_default("000000", config)


def _build_staleness_sys_default(org_id, config=None):
    if not config:
        config = inventory_config()

    return AttrDict(
        {
            "id": "system_default",
            "org_id": org_id,
            "conventional_time_to_stale": config.conventional_time_to_stale_seconds,
            "conventional_time_to_stale_warning": config.conventional_time_to_stale_warning_seconds,
            "conventional_time_to_delete": config.conventional_time_to_delete_seconds,
            "immutable_time_to_stale": config.immutable_time_to_stale_seconds,
            "immutable_time_to_stale_warning": config.immutable_time_to_stale_warning_seconds,
            "immutable_time_to_delete": config.immutable_time_to_delete_seconds,
            "created_on": "N/A",
            "modified_on": "N/A",
        }
    )


# This is required because we do not keep a ORM object that is attached to a session
# leaving in the global scope. Before this serialization,
# it was causing sqlalchemy.orm.exc.DetachedInstanceError
def _build_serialized_acc_staleness_obj(staleness):
    return AttrDict(
        {
            "id": str(staleness.id),
            "org_id": staleness.org_id,
            "conventional_time_to_stale": staleness.conventional_time_to_stale,
            "conventional_time_to_stale_warning": staleness.conventional_time_to_stale_warning,
            "conventional_time_to_delete": staleness.conventional_time_to_delete,
            "immutable_time_to_stale": staleness.immutable_time_to_stale,
            "immutable_time_to_stale_warning": staleness.immutable_time_to_stale_warning,
            "immutable_time_to_delete": staleness.immutable_time_to_delete,
            "created_on": staleness.created_on,
            "modified_on": staleness.modified_on,
        }
    )


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
