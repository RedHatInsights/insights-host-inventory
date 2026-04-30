import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import connexion
from flask_caching import Cache
from redis import Redis

from app.logging import get_logger

CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
CACHE = Cache(config=CACHE_CONFIG)
CACHE_PREFIX = "flask_cache_"
CACHE_TYPE_REDIS_CACHE = "RedisCache"
CACHE_EXECUTOR = None
REDIS_CLIENT = None
STALENESS_L2_CACHE_ENABLED = False
logger = get_logger("cache")


def init_cache(app_config, flask_app):
    global CACHE
    global CACHE_CONFIG
    global CACHE_EXECUTOR
    global REDIS_CLIENT
    global STALENESS_L2_CACHE_ENABLED
    cache_type = "NullCache"
    logger.info("Initializing Cache")

    if not CACHE_EXECUTOR:
        CACHE_EXECUTOR = ThreadPoolExecutor(app_config.api_cache_max_thread_pool_workers)
    CACHE_CONFIG = {"CACHE_TYPE": cache_type, "CACHE_DEFAULT_TIMEOUT": app_config.api_cache_timeout}
    if app_config.api_cache_type == CACHE_TYPE_REDIS_CACHE and app_config._cache_host and app_config._cache_port:
        CACHE_CONFIG["CACHE_TYPE"] = app_config.api_cache_type
        CACHE_CONFIG["CACHE_REDIS_HOST"] = app_config._cache_host
        CACHE_CONFIG["CACHE_REDIS_PORT"] = app_config._cache_port
        if not REDIS_CLIENT:
            REDIS_CLIENT = Redis(
                host=app_config._cache_host,
                port=app_config._cache_port,
                socket_timeout=app_config.redis_socket_timeout,
                socket_connect_timeout=app_config.redis_socket_connect_timeout,
            )
            logger.info("Instantiated Redis client")

    if STALENESS_L2_CACHE_ENABLED := (
        CACHE_CONFIG.get("CACHE_TYPE") == CACHE_TYPE_REDIS_CACHE and app_config.api_staleness_cache_enabled
    ):
        logger.info("Staleness L2 (Redis) cache is enabled")
    else:
        logger.info(
            "Staleness L2 (Redis) cache is disabled "
            "(requires INVENTORY_API_CACHE_TYPE=RedisCache, Redis host/port, and "
            "INVENTORY_API_STALENESS_CACHE_ENABLED=true)"
        )

    if not CACHE:
        logger.info(f"Cache is unset; using config={CACHE_CONFIG}")
        CACHE = Cache(config=CACHE_CONFIG)
    else:
        logger.info(f"Cache using config={CACHE_CONFIG}")

    if flask_app and flask_app.app and isinstance(flask_app, connexion.apps.flask.FlaskApp):
        logger.info("Cache initialized with app.")
        CACHE.init_app(flask_app.app, config=CACHE_CONFIG)
    else:
        logger.info(f"Cache not initialized with app. Passed the following for the app={flask_app}.")


def _get_redis_client():
    return REDIS_CLIENT


def _delete_keys_redis(cache_key, wildcard=True):
    global CACHE_CONFIG
    try:
        client = _get_redis_client()
        if wildcard:
            keys_to_delete = []
            # Use SCAN to find keys to delete that start with the prefix; default prefix is flask_cache_
            for key in client.scan_iter(f"{CACHE_PREFIX}{cache_key}*"):
                keys_to_delete.append(key)
            if keys_to_delete:
                client.delete(*keys_to_delete)
                logger.info(f"Deleted cache keys count: {len(keys_to_delete)}")
            else:
                logger.info(f"Found no matching cache keys for pattern: {CACHE_PREFIX}{cache_key}*")
        else:
            client.delete(f"{CACHE_PREFIX}{cache_key}")
            logger.info(f"Deleted single cache key: {CACHE_PREFIX}{cache_key}")
    except Exception as exec:
        logger.exception("Cache deletion failed", exc_info=exec)


def delete_keys(cache_key, wildcard=True, spawn=False):
    global CACHE_CONFIG
    global CACHE_EXECUTOR

    if CACHE_CONFIG and CACHE_CONFIG.get("CACHE_TYPE") == CACHE_TYPE_REDIS_CACHE and cache_key:
        if spawn and CACHE_EXECUTOR:
            logger.info("Submitted cache-deletion callable to executor")
            CACHE_EXECUTOR.submit(_delete_keys_redis, cache_key, wildcard)
        else:
            _delete_keys_redis(cache_key=cache_key, wildcard=wildcard)
    else:
        if not CACHE_CONFIG:
            logger.info("Not deleting cache: CACHE_CONFIG is falsy")
        elif not cache_key:
            logger.info("Not deleting cache: cache_key is falsy")
        else:
            cache_type = CACHE_CONFIG.get("CACHE_TYPE")
            logger.info(f"Not deleting cache: CACHE_TYPE '{cache_type}' != '{CACHE_TYPE_REDIS_CACHE}'")


def delete_cached_system_keys(insights_id=None, org_id=None, owner_id=None, spawn=False):
    if insights_id and org_id and owner_id:
        delete_keys(f"insights_id={insights_id}_org={org_id}_user=SYSTEM-{owner_id}", wildcard=False, spawn=spawn)
    elif insights_id and org_id and not owner_id:
        delete_keys(f"insights_id={insights_id}_org={org_id}", wildcard=True, spawn=spawn)
    elif not insights_id and org_id:
        delete_keys(f"insights_id=*_org={org_id}", wildcard=True, spawn=spawn)


def set_cached_system(system_key, host, config):
    global CACHE_CONFIG
    global CACHE

    if not CACHE:
        logger.info("Cache is unset when attampting to set value.")
        init_cache(config, None)
    try:
        CACHE.set(key=system_key, value=host, timeout=config.cache_insights_client_system_timeout_sec)
    except Exception as exec:
        logger.exception("Cache deletion failed", exc_info=exec)


# --- Staleness cache ---

STALENESS_CACHE_KEY_PREFIX = "hbi:staleness:"
_STALENESS_DATETIME_FIELDS = {"created_on", "modified_on"}


def _staleness_json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _deserialize_staleness_dict(data: dict):
    from app.staleness_serialization import AttrDict

    for field in _STALENESS_DATETIME_FIELDS:
        if data.get(field) is not None:
            data[field] = datetime.fromisoformat(data[field])
    return AttrDict(data)


def get_cached_staleness(org_id: str):
    if not STALENESS_L2_CACHE_ENABLED:
        logger.debug("Staleness L2 cache disabled (Redis API cache off or staleness cache flag off)")
        return None
    try:
        client = _get_redis_client()
        key = f"{STALENESS_CACHE_KEY_PREFIX}{org_id}"
        raw = client.get(key)
        if raw is None:
            logger.debug(f"Staleness cache miss for org_id={org_id} (key={key})")
            return None
        logger.debug(f"Staleness cache hit for org_id={org_id} (key={key})")
        return _deserialize_staleness_dict(json.loads(raw))
    except Exception as exc:
        logger.warning("Failed to get cached staleness", exc_info=exc)
        return None


def set_cached_staleness(org_id: str, staleness_obj, timeout: int):
    if not STALENESS_L2_CACHE_ENABLED:
        logger.debug(f"Staleness L2 cache disabled; skipping set for org_id={org_id}")
        return
    try:
        client = _get_redis_client()
        key = f"{STALENESS_CACHE_KEY_PREFIX}{org_id}"
        serialized = json.dumps(dict(staleness_obj), default=_staleness_json_default)
        client.set(key, serialized, ex=timeout)
        logger.debug(f"Staleness cache set for org_id={org_id} (key={key}, timeout={timeout}s)")
    except Exception as exc:
        logger.exception("Failed to set cached staleness", exc_info=exc)


def delete_cached_staleness(org_id: str):
    if not STALENESS_L2_CACHE_ENABLED:
        logger.debug(f"Staleness L2 cache disabled; skipping delete for org_id={org_id}")
        return
    try:
        client = _get_redis_client()
        key = f"{STALENESS_CACHE_KEY_PREFIX}{org_id}"
        client.delete(key)
        logger.debug(f"Staleness cache deleted for org_id={org_id} (key={key})")
    except Exception as exc:
        logger.exception("Failed to delete cached staleness", exc_info=exc)
