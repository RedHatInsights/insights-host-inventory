import connexion
import yaml
from connexion.resolver import RestyResolver
from flask import current_app
from flask import jsonify
from flask import request
from prometheus_flask_exporter import PrometheusMetrics

from api.mgmt import monitoring_blueprint
from app import payload_tracker
from app.config import Config
from app.exceptions import InventoryException
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import db
from app.queue.event_producer import EventProducer
from app.validators import verify_uuid_format  # noqa: 401

logger = get_logger(__name__)

IDENTITY_HEADER = "x-rh-identity"
REQUEST_ID_HEADER = "x-rh-insights-request-id"
UNKNOWN_REQUEST_ID_VALUE = "-1"


def render_exception(exception):
    response = jsonify(exception.to_json())
    response.status_code = exception.status
    return response


def inventory_config():
    return current_app.config["INVENTORY_CONFIG"]


def create_app(runtime_environment):
    connexion_options = {"swagger_ui": True}

    # This feels like a hack but it is needed.  The logging configuration
    # needs to be setup before the flask app is initialized.
    configure_logging(runtime_environment)

    app_config = Config(runtime_environment)
    app_config.log_configuration()

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

    flask_app.config["INVENTORY_CONFIG"] = app_config

    db.init_app(flask_app)

    flask_app.register_blueprint(monitoring_blueprint, url_prefix=app_config.mgmt_url_path_prefix)

    @flask_app.before_request
    def set_request_id():
        threadctx.request_id = request.headers.get(REQUEST_ID_HEADER, UNKNOWN_REQUEST_ID_VALUE)

    if runtime_environment.event_producer_enabled:
        flask_app.event_producer = EventProducer(app_config)
    else:
        logger.warning(
            "WARNING: The event producer has been disabled.  "
            "The message queue based event notifications have been disabled."
        )

    payload_tracker_producer = None
    if not runtime_environment.payload_tracker_enabled:
        # If we are running in "testing" mode, then inject the NullProducer.
        payload_tracker_producer = payload_tracker.NullProducer()

        logger.warning(
            "WARNING: Using the NullProducer for the payload tracker producer.  "
            "No payload tracker events will be sent to to payload tracker."
        )

    payload_tracker.init_payload_tracker(app_config, producer=payload_tracker_producer)

    # HTTP request metrics
    if runtime_environment.metrics_endpoint_enabled:
        PrometheusMetrics(
            flask_app,
            defaults_prefix="inventory",
            group_by="url_rule",
            path=None,
            excluded_paths=["^/metrics$", "^/health$", "^/version$", r"^/favicon\.ico$"],
        )

    return flask_app
