import os
import connexion
import yaml

from flask_sqlalchemy import SQLAlchemy
from connexion.resolver import RestyResolver
from api.mgmt import management


db = SQLAlchemy()


def _build_database_uri():
    user = os.getenv("INVENTORY_DB_USER", "insights")
    password = os.getenv("INVENTORY_DB_PASS", "insights")
    host = os.getenv("INVENTORY_DB_HOST", "localhost")
    db_name = os.getenv("INVENTORY_DB_NAME", "test_db")

    return f"postgresql://{user}:{password}@{host}/{db_name}"


def _get_db_pool_timeout():
    return int(os.getenv("INVENTORY_DB_POOL_TIMEOUT", "5"))


def _get_db_pool_size():
    return int(os.getenv("INVENTORY_DB_POOL_SIZE", "5"))


def _get_base_url_path():
    app_name = os.getenv("APP_NAME", "inventory")
    path_prefix = os.getenv("PATH_PREFIX", "/r/insights/platform")
    path = f"{path_prefix}/{app_name}"
    return path


def _get_api_path():
    base_url_path = _get_base_url_path()
    version = "v1"
    path = f"{base_url_path}/api/{version}"
    return path


def create_app(config_name):
    connexion_options = {"swagger_ui": True}

    url_path = _get_api_path()
    if config_name != "testing":
        print("URL Path:%s" % url_path)

    connexion_app = connexion.App(
        "inventory", specification_dir="./swagger/", options=connexion_options
    )

    # Read the swagger.yml file to configure the endpoints
    with open("swagger/api.spec.yaml", "rb") as fp:
        spec = yaml.safe_load(fp)

    # If we want to disable auth we first make the header not required
    if os.getenv("FLASK_DEBUG") and os.getenv("NOAUTH"):
        spec["parameters"]["rhIdentityHeader"]["required"] = False

    connexion_app.add_api(
        spec,
        arguments={"title": "RestyResolver Example"},
        resolver=RestyResolver("api"),
        validate_responses=True,
        strict_validation=True,
        base_path=url_path,
    )

    flask_app = connexion_app.app

    flask_app.config["SQLALCHEMY_ECHO"] = False
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = _build_database_uri()
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SQLALCHEMY_POOL_SIZE"] = _get_db_pool_size()
    flask_app.config["SQLALCHEMY_POOL_TIMEOUT"] = _get_db_pool_timeout()

    db.init_app(flask_app)

    flask_app.register_blueprint(management, url_prefix=_get_base_url_path())

    return flask_app
