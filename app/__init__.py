import os
import connexion
import logging
import logging.config
import yaml

from connexion.resolver import RestyResolver
from flask import jsonify

from api.mgmt import monitoring_blueprint
from app.config import Config
from app.models import db
from app.exceptions import InventoryException
from app.validators import verify_uuid_format


def render_exception(exception):
    response = jsonify(exception.to_json())
    response.status_code = exception.status
    return response


def create_app(config_name):
    connexion_options = {"swagger_ui": True}

    # This feels like a hack but it is needed.  The logging configuration
    # needs to be setup before the flask app is initialized.
    configure_logging()

    app_config = Config(config_name)

    connexion_app = connexion.App(
        "inventory", specification_dir="./swagger/", options=connexion_options
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
        base_path=app_config.api_url_path_prefix,
    )

    # Add an error handler that will convert our top level exceptions
    # into error responses
    connexion_app.add_error_handler(InventoryException, render_exception)

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


def configure_logging():
    env_var_name = "INVENTORY_LOGGING_CONFIG_FILE"
    log_config_file = os.getenv(env_var_name)
    if log_config_file is not None:
        # The logging module throws an odd error (KeyError) if the
        # config file is not found.  Hopefully, this makes it more clear.
        try:
            fh = open(log_config_file)
            fh.close()
        except FileNotFoundError:
            print("Error reading the logging configuration file.  "
                  "Verify the %s environment variable is set "
                  "correctly. Aborting..." % env_var_name)
            raise

        logging.config.fileConfig(fname=log_config_file)
