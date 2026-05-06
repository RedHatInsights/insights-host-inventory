from datetime import UTC
from datetime import datetime

from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm.base import instance_state

from api.cache import delete_cached_staleness
from api.cache import get_cached_staleness
from api.cache import set_cached_staleness
from app.common import inventory_config
from app.culling import Timestamps
from app.logging import get_logger
from app.staleness_serialization import build_serialized_acc_staleness_obj
from app.staleness_serialization import build_staleness_sys_default
from app.staleness_serialization import get_staleness_timestamps
from lib.batch_cache import ThreadLocalBatchCache

logger = get_logger(__name__)


class StalenessCache(ThreadLocalBatchCache):
    """Two-tier cache for staleness config lookups, keyed by org_id.

    L1: thread-local dict (batch-scoped, zero I/O).
    L2: Redis (cross-request, survives batch boundaries).
    """

    @classmethod
    def get(cls, key):
        result = super().get(key)
        if result is not None:
            return result

        result = get_cached_staleness(key)
        if result is not None:
            super().put(key, result)
        return result

    @classmethod
    def put(cls, key, value):
        super().put(key, value)

        try:
            timeout = inventory_config().staleness_cache_timeout
            set_cached_staleness(key, value, timeout)
        except Exception:
            logger.exception("Failed to write staleness to Redis for org_id=%s", key)

    @classmethod
    def delete(cls, key):
        super().delete(key)
        delete_cached_staleness(key)


def get_staleness_obj(org_id):
    cached = StalenessCache.get(org_id)
    if cached is not None:
        return cached

    try:
        from app.models.staleness import Staleness

        staleness = Staleness.query.filter(Staleness.org_id == org_id).one()
        logger.info("Using custom account staleness")
        staleness = build_serialized_acc_staleness_obj(staleness)
    except NoResultFound:
        logger.debug(f"No staleness data found for org {org_id}, using system default values for model")
        staleness = build_staleness_sys_default(org_id)

    StalenessCache.put(org_id, staleness)
    return staleness


def _set_display_name_on_save(context):
    params = context.get_current_parameters()
    if not params["display_name"] or params["display_name"] == str(params["id"]):
        return params.get("fqdn") or params["id"]


def _time_now():
    return datetime.now(UTC)


def _create_staleness_timestamps_values(host, org_id):
    staleness = get_staleness_obj(org_id)
    staleness_ts = Timestamps.from_config(inventory_config())
    return get_staleness_timestamps(host, staleness_ts, staleness)


def deleted_by_this_query(model):
    return not instance_state(model).expired
