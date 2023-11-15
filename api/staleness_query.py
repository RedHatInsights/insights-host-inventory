from sqlalchemy.orm.exc import NoResultFound

from app import inventory_config
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
            "conventional_staleness_delta": config.conventional_staleness_seconds,
            "conventional_stale_warning_delta": config.conventional_stale_warning_seconds,
            "conventional_deletion_delta": config.conventional_culling_seconds,
            "immutable_staleness_delta": config.immutable_staleness_seconds,
            "immutable_stale_warning_delta": config.immutable_stale_warning_seconds,
            "immutable_deletion_delta": config.immutable_culling_seconds,
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
            "conventional_staleness_delta": staleness.conventional_staleness_delta,
            "conventional_stale_warning_delta": staleness.conventional_stale_warning_delta,
            "conventional_deletion_delta": staleness.conventional_deletion_delta,
            "immutable_staleness_delta": staleness.immutable_staleness_delta,
            "immutable_stale_warning_delta": staleness.immutable_stale_warning_delta,
            "immutable_deletion_delta": staleness.immutable_deletion_delta,
            "created_on": staleness.created_on,
            "modified_on": staleness.modified_on,
        }
    )


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
