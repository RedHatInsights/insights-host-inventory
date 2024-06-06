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
        CACHE = CACHE.init_app(flask_app, config=cache_config)


def _delete_keys_simple(prefix):
    cache_dict = CACHE.cache._cache
    for cache_key in list(cache_dict.keys()):
        if cache_key.startswith(prefix):
            cache_dict.pop(cache_key)


def _delete_keys_redis(prefix):
    redis_client = CACHE.cache._client
    # Use SCAN to find keys to delete that start with the prefix
    for key in redis_client.scan_iter(f"{prefix}*"):
        redis_client.delete(key)


def delete_keys(prefix):
    if CACHE and CACHE.config["CACHE_TYPE"] == "SimpleCache":
        _delete_keys_simple(prefix)

    if CACHE and CACHE.config["CACHE_TYPE"] == "RedisCache":
        _delete_keys_redis(prefix)
