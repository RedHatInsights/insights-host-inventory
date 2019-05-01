import os
import connexion
import yaml

from connexion.resolver import RestyResolver
from flask import jsonify, request

from api.mgmt import monitoring_blueprint
from app.config import Config
from app.models import db
from app.exceptions import InventoryException
from app.logging import configure_logging, threadctx
from app.validators import verify_uuid_format  # noqa: 401
from tasks import start_consumer

REQUEST_ID_HEADER = "x-rh-insights-request-id"
UNKNOWN_REQUEST_ID_VALUE = "-1"


def render_exception(exception):
    response = jsonify(exception.to_json())
    response.status_code = exception.status
    return response


def create_app(config_name):
    connexion_options = {"swagger_ui": True}

    # This feels like a hack but it is needed.  The logging configuration
    # needs to be setup before the flask app is initialized.
    configure_logging(config_name)

    app_config = Config(config_name)

    connexion_app = connexion.App(
        "inventory", specification_dir="./swagger/", options=connexion_options
    )

    # Read the swagger.yml file to configure the endpoints
    with open("swagger/api.spec.yaml", "rb") as fp:
        spec = yaml.safe_load(fp)

    for api_url in app_config.api_urls:
        if api_url:
            connexion_app.add_api(
                spec,
                arguments={"title": "RestyResolver Example"},
                resolver=RestyResolver("api"),
                validate_responses=True,
                strict_validation=True,
                base_path=api_url,
            )
            app_config.logger.info("Listening on API: %s" % api_url)

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

    @flask_app.before_request
    def set_request_id():
        threadctx.request_id = request.headers.get(
            REQUEST_ID_HEADER,
            UNKNOWN_REQUEST_ID_VALUE)

    if all(map(os.environ.get, ["KAFKA_TOPIC", "KAFKA_GROUP", "KAFKA_BOOTSTRAP_SERVERS"])):
        start_consumer(flask_app)

    return flask_app
