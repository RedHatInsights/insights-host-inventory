import connexion
from flask_caching import Cache
from redis import Redis

from app.logging import get_logger

CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
CACHE = Cache(config=CACHE_CONFIG)
logger = get_logger("cache")


def init_cache(app_config, flask_app):
    global CACHE
    global CACHE_CONFIG
    cache_type = "NullCache"
    logger.info("Initializing Cache")
    if app_config.api_cache_timeout:
        cache_type = "SimpleCache"

    CACHE_CONFIG = {"CACHE_TYPE": cache_type, "CACHE_DEFAULT_TIMEOUT": app_config.api_cache_timeout}
    if app_config.api_cache_type == "RedisCache" and app_config._cache_host and app_config._cache_port:
        CACHE_CONFIG["CACHE_TYPE"] = app_config.api_cache_type
        CACHE_CONFIG["CACHE_REDIS_HOST"] = app_config._cache_host
        CACHE_CONFIG["CACHE_REDIS_PORT"] = app_config._cache_port

    if not CACHE:
        logger.info(f"Cache is unset; using config={CACHE_CONFIG}")
        CACHE = Cache(config=CACHE_CONFIG)
    else:
        logger.info(f"Cache using config={CACHE_CONFIG}")

    if flask_app and flask_app.app and isinstance(flask_app, connexion.apps.flask.FlaskApp) and not CACHE.app:
        logger.info("Cache initialized with app.")
        CACHE.init_app(flask_app.app, config=CACHE_CONFIG)
    else:
        logger.info(f"Cache not initialized with app. Passed the following for the app={flask_app}.")


def _delete_keys_simple(prefix):
    global CACHE
    if not CACHE:
        return
    cache_dict = CACHE.cache._cache
    for cache_key in list(cache_dict.keys()):
        if cache_key.startswith(f"flask_cache_{prefix}"):
            cache_dict.pop(cache_key)


def _delete_keys_redis(prefix):
    global CACHE_CONFIG
    try:
        redis_client = Redis(host=CACHE_CONFIG.get("CACHE_REDIS_HOST"), port=CACHE_CONFIG.get("CACHE_REDIS_PORT"))
        # Use SCAN to find keys to delete that start with the prefix; default prefix is flask_cache_
        for key in redis_client.scan_iter(f"flask_cache_{prefix}*"):
            redis_client.delete(key)
    except Exception as exec:
        logger.exception("Cache deletion failed", exc_info=exec)


def delete_keys(prefix):
    global CACHE_CONFIG
    if CACHE_CONFIG and CACHE_CONFIG.get("CACHE_TYPE") == "SimpleCache" and prefix:
        _delete_keys_simple(prefix)

    if CACHE_CONFIG and CACHE_CONFIG.get("CACHE_TYPE") == "RedisCache" and prefix:
        _delete_keys_redis(prefix)


def delete_cached_system_keys(insights_id=None, org_id=None):
    if insights_id:
        delete_keys(f"insights_id={insights_id}")
    if org_id:
        delete_keys(f"insights_id=*_org={org_id}")


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
