from flask import Flask
from flask_caching import Cache


CACHE = Cache(config={"CACHE_TYPE": None})


def init_cache(app_config, flask_app):
    global CACHE
    cache_type = "NullCache"

    if app_config.api_cache_timeout:
        cache_type = "SimpleCache"

    cache_config = {"CACHE_TYPE": cache_type, "CACHE_DEFAULT_TIMEOUT": app_config.api_cache_timeout}
    if app_config.api_cache_type == "RedisCache" and app_config._cache_host and app_config._cache_port:
        cache_config["CACHE_TYPE"] = app_config.api_cache_type
        cache_config["CACHE_REDIS_HOST"] = app_config._cache_host
        cache_config["CACHE_REDIS_PORT"] = app_config._cache_port

    if not CACHE:
        CACHE = Cache(config=cache_config)
    if isinstance(flask_app, Flask):
        CACHE = CACHE.init_app(flask_app, config=cache_config)
