import yaml

import connexion
from api.mgmt import monitoring_blueprint
from app.config import Config
from app.exceptions import InventoryException
from app.logging import configure_logging
from app.models import db
from connexion.resolver import RestyResolver
from marshmallow import ValidationError

from .error_handlers import render_exception, validation_error_handler


def create_app(config_name):
    connexion_options = {"swagger_ui": True}

    # This feels like a hack but it is needed.  The logging configuration
    # needs to be setup before the flask app is initialized.
    configure_logging(config_name)

    app_config = Config(config_name)

    connexion_app = connexion.App(
        "inventory",
        specification_dir="./swagger/",
        options=connexion_options
    )

    # Read the swagger.yml file to configure the endpoints
    with open("swagger/api.spec.yaml", "rb") as fp:
        spec = yaml.safe_load(fp)

    connexion_app.add_api(
        spec,
        arguments={"title": "RestyResolver Example"},
        resolver=RestyResolver("api"),
        validate_responses=True,
        strict_validation=True,
        base_path=app_config.api_url_path_prefix
    )

    # Add an error handler that will convert our top level exceptions
    # into error responses
    connexion_app.add_error_handler(InventoryException, render_exception)
    connexion_app.add_error_handler(ValidationError, validation_error_handler)

    flask_app = connexion_app.app

    flask_app.config["SQLALCHEMY_ECHO"] = False
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = app_config.db_uri
    flask_app.config["SQLALCHEMY_POOL_SIZE"] = app_config.db_pool_size
    flask_app.config["SQLALCHEMY_POOL_TIMEOUT"] = app_config.db_pool_timeout

    db.init_app(flask_app)

    flask_app.register_blueprint(monitoring_blueprint,
                                 url_prefix=app_config.mgmt_url_path_prefix)

    return flask_app
