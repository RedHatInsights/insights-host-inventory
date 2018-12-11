import os
import connexion
import yaml

from connexion.resolver import RestyResolver
from flask import jsonify

from app.config import Config
from app.models import db
from app.exceptions import InventoryException


def render_exception(exception):
    response = jsonify(exception.to_json())
    response.status_code = exception.status
    return response


def create_app(config_name):
    connexion_options = {"swagger_ui": True}

    app_config = Config(config_name)

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
        base_path=app_config.getApiPath(),
    )

    # Add an error handler that will convert our top level exceptions
    # into error responses
    connexion_app.add_error_handler(InventoryException, render_exception)

    flask_app = connexion_app.app

    flask_app.config["SQLALCHEMY_ECHO"] = False
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = app_config.getDBUri()
    flask_app.config["SQLALCHEMY_POOL_SIZE"] = app_config.getDBPoolSize()
    flask_app.config["SQLALCHEMY_POOL_TIMEOUT"] = app_config.getDBPoolTimeout()

    db.init_app(flask_app)

    return flask_app
