from datetime import UTC
from datetime import datetime

from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm.base import instance_state

from app.common import inventory_config
from app.culling import Timestamps
from app.logging import get_logger
from app.staleness_serialization import build_serialized_acc_staleness_obj
from app.staleness_serialization import build_staleness_sys_default
from app.staleness_serialization import get_staleness_timestamps

logger = get_logger(__name__)


def _get_staleness_obj(org_id):
    try:
        from app.models.staleness import Staleness

        staleness = Staleness.query.filter(Staleness.org_id == org_id).one()
        logger.info("Using custom account staleness")
        staleness = build_serialized_acc_staleness_obj(staleness)
    except NoResultFound:
        logger.debug(f"No staleness data found for org {org_id}, using system default values for model")
        staleness = build_staleness_sys_default(org_id)
        return staleness

    return staleness


def _set_display_name_on_save(context):
    params = context.get_current_parameters()
    if not params["display_name"] or params["display_name"] == str(params["id"]):
        return params["canonical_facts"].get("fqdn") or params["id"]


def _time_now():
    return datetime.now(UTC)


def _create_staleness_timestamps_values(host, org_id):
    staleness = _get_staleness_obj(org_id)
    staleness_ts = Timestamps.from_config(inventory_config())
    return get_staleness_timestamps(host, staleness_ts, staleness)


def deleted_by_this_query(model):
    return not instance_state(model).expired
