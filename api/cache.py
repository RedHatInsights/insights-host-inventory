from flask import Flask
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
    if isinstance(flask_app, Flask):
        logger.info("Cache initialized with app.")
        CACHE = CACHE.init_app(flask_app, config=CACHE_CONFIG)
    else:
        logger.info(f"Cache not initialized with app. Passed the following for the app={flask_app}.")


def _delete_keys_simple(prefix):
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
    if CACHE and CACHE.config["CACHE_TYPE"] == "SimpleCache":
        _delete_keys_simple(prefix)

    if CACHE and CACHE.config["CACHE_TYPE"] == "RedisCache":
        _delete_keys_redis(prefix)
