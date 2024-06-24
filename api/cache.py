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
