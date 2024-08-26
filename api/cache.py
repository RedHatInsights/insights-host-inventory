from concurrent.futures import ThreadPoolExecutor

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
logger = get_logger("cache")


def init_cache(app_config, flask_app):
    global CACHE
    global CACHE_CONFIG
    global CACHE_EXECUTOR
    cache_type = "NullCache"
    logger.info("Initializing Cache")

    CACHE_EXECUTOR = ThreadPoolExecutor(app_config.api_cache_max_thread_pool_workers)
    CACHE_CONFIG = {"CACHE_TYPE": cache_type, "CACHE_DEFAULT_TIMEOUT": app_config.api_cache_timeout}
    if app_config.api_cache_type == CACHE_TYPE_REDIS_CACHE and app_config._cache_host and app_config._cache_port:
        CACHE_CONFIG["CACHE_TYPE"] = app_config.api_cache_type
        CACHE_CONFIG["CACHE_REDIS_HOST"] = app_config._cache_host
        CACHE_CONFIG["CACHE_REDIS_PORT"] = app_config._cache_port

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


def _delete_keys_redis(cache_key, wildcard=True):
    global CACHE_CONFIG
    global REDIS_CLIENT
    try:
        if not REDIS_CLIENT:
            REDIS_CLIENT = Redis(host=CACHE_CONFIG.get("CACHE_REDIS_HOST"), port=CACHE_CONFIG.get("CACHE_REDIS_PORT"))
            logger.info("Instantiated Redis client")
        if wildcard:
            keys_to_delete = []
            # Use SCAN to find keys to delete that start with the prefix; default prefix is flask_cache_
            for key in REDIS_CLIENT.scan_iter(f"{CACHE_PREFIX}{cache_key}*"):
                keys_to_delete.append(key)
            if keys_to_delete:
                REDIS_CLIENT.delete(*keys_to_delete)
                logger.info(f"Deleted cache keys count: {len(keys_to_delete)}")
            else:
                logger.info(f"Found no matching cache keys for pattern: {CACHE_PREFIX}{cache_key}*")
        else:
            REDIS_CLIENT.delete(f"{CACHE_PREFIX}{cache_key}")
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
