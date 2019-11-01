import connexion
import yaml
from connexion.resolver import RestyResolver
from flask import jsonify
from flask import request

from api.mgmt import monitoring_blueprint
from app import payload_tracker
from app.config import Config
from app.exceptions import InventoryException
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import db
from app.validators import verify_uuid_format  # noqa: 401
from tasks import init_tasks

logger = get_logger(__name__)

REQUEST_ID_HEADER = "x-rh-insights-request-id"
UNKNOWN_REQUEST_ID_VALUE = "-1"


def render_exception(exception):
    response = jsonify(exception.to_json())
    response.status_code = exception.status
    return response


def create_app(config_name, start_tasks=False, start_payload_tracker=False):
    connexion_options = {"swagger_ui": True}

    # This feels like a hack but it is needed.  The logging configuration
    # needs to be setup before the flask app is initialized.
    configure_logging(config_name)

    app_config = Config()
    app_config.log_configuration(config_name)

    connexion_app = connexion.App("inventory", specification_dir="./swagger/", options=connexion_options)

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
            logger.info("Listening on API: %s", api_url)

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

    flask_app.register_blueprint(monitoring_blueprint, url_prefix=app_config.mgmt_url_path_prefix)

    @flask_app.before_request
    def set_request_id():
        threadctx.request_id = request.headers.get(REQUEST_ID_HEADER, UNKNOWN_REQUEST_ID_VALUE)

    if start_tasks:
        init_tasks(app_config, flask_app)
    else:
        logger.warning(
            'WARNING: The "tasks" subsystem has been disabled.  '
            "The message queue based system_profile consumer "
            "and message queue based event notifications have been disabled."
        )

    payload_tracker_producer = None
    if start_payload_tracker is False:
        # If we are running in "testing" mode, then inject the NullProducer.
        payload_tracker_producer = payload_tracker.NullProducer()

        logger.warning(
            "WARNING: Using the NullProducer for the payload tracker producer.  "
            "No payload tracker events will be sent to to payload tracker."
        )

    payload_tracker.init_payload_tracker(app_config, producer=payload_tracker_producer)

    return flask_app
