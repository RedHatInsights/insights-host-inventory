import os
import connexion
import yaml

from connexion.resolver import RestyResolver
from flask import jsonify

from app.models import db
from app.exceptions import InventoryException


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


def _get_api_path():
    app_name = os.getenv("APP_NAME", "inventory")
    path_prefix = os.getenv("PATH_PREFIX", "/r/insights/platform")

    version = "v1"

    path = f"{path_prefix}/{app_name}/api/{version}"
    return path


def render_exception(exception):
    response = jsonify(exception.to_json())
    response.status_code = exception.status
    return response


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

    # Add an error handler that will convert our top level exceptions
    # into error responses
    connexion_app.add_error_handler(InventoryException, render_exception)

    flask_app = connexion_app.app

    flask_app.config["SQLALCHEMY_ECHO"] = False
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = _build_database_uri()
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SQLALCHEMY_POOL_SIZE"] = _get_db_pool_size()
    flask_app.config["SQLALCHEMY_POOL_TIMEOUT"] = _get_db_pool_timeout()

    db.init_app(flask_app)

    return flask_app
