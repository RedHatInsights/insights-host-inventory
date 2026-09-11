import json
from datetime import datetime

import connexion
from flask_caching import Cache
from redis import Redis

from api.system_cache_key import system_cache_key_base
from app.logging import get_logger

CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
CACHE = Cache(config=CACHE_CONFIG)
CACHE_PREFIX = "flask_cache_"
CACHE_TYPE_REDIS_CACHE = "RedisCache"
REDIS_CLIENT = None
STALENESS_L2_CACHE_ENABLED = False
GENERATION_KEY_SUFFIX = ":gen"
logger = get_logger("cache")


def init_cache(app_config, flask_app):
    global CACHE
    global CACHE_CONFIG
    global REDIS_CLIENT
    global STALENESS_L2_CACHE_ENABLED
    cache_type = "NullCache"
    logger.info("Initializing Cache")

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


def _generation_key(base_key: str) -> str:
    return f"{CACHE_PREFIX}{base_key}{GENERATION_KEY_SUFFIX}"


def get_system_cache_generation(insights_id, org_id, owner_id):
    """Read the current cache generation counter for a system cache entry.

    Returns 0 when Redis is unavailable or the generation key does not exist.
    When the key is absent, it is lazily initialised to 0 with the standard
    cache TTL so that subsequent lookups are Redis cache-hits.
    """
    if not (CACHE_CONFIG and CACHE_CONFIG.get("CACHE_TYPE") == CACHE_TYPE_REDIS_CACHE):
        return 0
    try:
        from app.common import inventory_config

        client = _get_redis_client()
        base_key = system_cache_key_base(insights_id, org_id, owner_id)
        gen_key = _generation_key(base_key)
        value = client.get(gen_key)
        if value is not None:
            return int(value)
        # Key does not exist — lazily initialise to 0 so future GETs are
        # cache hits instead of misses.  NX prevents overwriting a counter
        # that was just incremented by a concurrent invalidation.
        gen_ttl = inventory_config().cache_insights_client_system_timeout_sec
        if client.set(gen_key, 0, ex=gen_ttl, nx=True):
            return 0
        # SET NX failed — another process created the key (e.g. INCR from
        # a concurrent invalidation).  Re-read to get the actual generation.
        current_value = client.get(gen_key)
        return int(current_value) if current_value is not None else 0
    except Exception as exc:
        logger.exception("Failed to read system cache generation", exc_info=exc)
        return 0


def _invalidate_system_cache_redis(insights_id, org_id, owner_id):
    """Increment the generation counter, making all current cache entries unreachable.

    Sets a TTL on the generation counter equal to the cache TTL so counters
    for hosts that are no longer accessed are automatically cleaned up.
    """
    try:
        from app.common import inventory_config

        client = _get_redis_client()
        base_key = system_cache_key_base(insights_id, org_id, owner_id)
        gen_key = _generation_key(base_key)
        gen_ttl = inventory_config().cache_insights_client_system_timeout_sec
        pipe = client.pipeline(transaction=False)
        pipe.incr(gen_key)
        pipe.expire(gen_key, gen_ttl)
        results = pipe.execute()
        new_gen = results[0]
        logger.info("Invalidated system cache for base_key=%s new_generation=%s", base_key, new_gen)
    except Exception as exc:
        logger.exception("System cache invalidation failed", exc_info=exc)


def _invalidate_system_cache(insights_id, org_id, owner_id):
    if not (CACHE_CONFIG and CACHE_CONFIG.get("CACHE_TYPE") == CACHE_TYPE_REDIS_CACHE):
        if not CACHE_CONFIG:
            logger.info("Not invalidating cache: CACHE_CONFIG is falsy")
        else:
            cache_type = CACHE_CONFIG.get("CACHE_TYPE")
            logger.info(f"Not invalidating cache: CACHE_TYPE '{cache_type}' != '{CACHE_TYPE_REDIS_CACHE}'")
        return

    _invalidate_system_cache_redis(insights_id, org_id, owner_id)


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


def delete_keys(cache_key, wildcard=True):
    global CACHE_CONFIG

    if CACHE_CONFIG and CACHE_CONFIG.get("CACHE_TYPE") == CACHE_TYPE_REDIS_CACHE and cache_key:
        _delete_keys_redis(cache_key=cache_key, wildcard=wildcard)
    else:
        if not CACHE_CONFIG:
            logger.info("Not deleting cache: CACHE_CONFIG is falsy")
        elif not cache_key:
            logger.info("Not deleting cache: cache_key is falsy")
        else:
            cache_type = CACHE_CONFIG.get("CACHE_TYPE")
            logger.info(f"Not deleting cache: CACHE_TYPE '{cache_type}' != '{CACHE_TYPE_REDIS_CACHE}'")


def delete_cached_system_keys(insights_id=None, org_id=None, owner_id=None):
    if insights_id and org_id and owner_id:
        _invalidate_system_cache(insights_id, org_id, owner_id)
    elif insights_id and org_id and not owner_id:
        delete_keys(f"insights_id={insights_id}_org={org_id}", wildcard=True)
    elif not insights_id and org_id:
        delete_keys(f"insights_id=*_org={org_id}", wildcard=True)


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
