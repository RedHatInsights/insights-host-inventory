import base64
import json
import os
from enum import Enum
from os.path import join

import connexion
import segment.analytics as analytics
import yaml
from connexion.options import SwaggerUIOptions
from connexion.resolver import RestyResolver
from flask import current_app
from flask import jsonify
from flask import request
from prance import _TranslatingParser as TranslatingParser
from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics

from api.cache import init_cache
from api.mgmt import monitoring_blueprint
from api.parsing import customURIParser
from api.spec import spec_blueprint
from app import payload_tracker
from app.config import Config
from app.custom_validator import build_validator_map
from app.exceptions import InventoryException
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import SPECIFICATION_DIR
from app.models import db
from app.queue.event_producer import EventProducer
from app.queue.events import EventType
from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success
from app.queue.metrics import notification_event_producer_failure
from app.queue.metrics import notification_event_producer_success
from app.queue.metrics import rbac_access_denied
from app.queue.notifications import NotificationType
from app.tags_blueprint import tags_bp
from lib.check_org import check_org_id
from lib.feature_flags import SchemaStrategy
from lib.feature_flags import init_unleash_app, get_flag_value, FLAG_INVENTORY_KESSEL_HOST_MIGRATION
from lib.kessel import init_kessel
from lib.handlers import register_shutdown

logger = get_logger(__name__)

IDENTITY_HEADER = "x-rh-identity"
REQUEST_ID_HEADER = "x-rh-insights-request-id"

SPECIFICATION_FILE = join(SPECIFICATION_DIR, "openapi.json")
SYSTEM_PROFILE_SPECIFICATION_FILE = join(SPECIFICATION_DIR, "system_profile.spec.yaml")
SYSTEM_PROFILE_BLOCK_LIST_FILE = join(SPECIFICATION_DIR, "system_profile_block_list.yaml")

SPEC_TYPES_LOOKUP = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict}

custom_filter_fields = ["operating_system"]

ORG_ID_CHECK_ENDPOINTS = [
    "api_host_get_host_list",
    "api_host_delete_hosts_by_filter",
    "api_host_delete_host_by_id",
    "api_host_get_host_by_id",
    "api_host_get_host_system_profile_by_id",
    "api_host_patch_host_by_id",
    "api_host_replace_facts",
    "api_host_merge_facts",
    "api_host_host_checkin",
    "api_staleness_get_staleness",
    "api_staleness_get_default_staleness",
    "api_staleness_create_staleness",
    "api_staleness_delete_staleness",
    "api_staleness_update_staleness",
    "api_group_get_group_list",
    "api_group_create_group",
    "api_group_patch_group_by_id",
    "api_group_delete_groups",
    "api_group_get_groups_by_id",
    "api_group_delete_hosts_from_group",
    "api_group_delete_hosts_from_different_groups",
]


class RbacPermission(Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "*"


class RbacResourceType(Enum):
    HOSTS = "hosts"
    GROUPS = "groups"
    STALENESS = "staleness"
    ALL = "*"


def initialize_metrics(config):
    event_topic_name = config.event_topic
    notification_topic_name = config.notification_topic
    for event_type in EventType:
        event_producer_failure.labels(event_type=event_type.name, topic=event_topic_name)
        event_producer_success.labels(event_type=event_type.name, topic=event_topic_name)

    for notification_type in NotificationType:
        notification_event_producer_failure.labels(
            notification_type=notification_type.name, topic=notification_topic_name
        )
        notification_event_producer_success.labels(
            notification_type=notification_type.name, topic=notification_topic_name
        )

    rbac_access_denied.labels(
        required_permission=f"inventory:{RbacResourceType.HOSTS.value}:{RbacPermission.READ.value}"
    )
    rbac_access_denied.labels(
        required_permission=f"inventory:{RbacResourceType.HOSTS.value}:{RbacPermission.WRITE.value}"
    )


#
# Registering analytics.flush directly with register_shutdown()
# results in errors during test suite cleanup.
# Adding this wrapper fixes the problem.
#
def flush_segmentio():
    if analytics.write_key:
        analytics.flush()


def initialize_segmentio():
    logger.info("Initializing Segmentio")
    analytics.write_key = os.getenv("SEGMENTIO_WRITE_KEY", None)
    logger.info("Registering Segmentio flush on shutdown")
    register_shutdown(flush_segmentio, "Flushing Segmentio queue")


def render_exception(exception):
    response = jsonify(exception.to_json())
    response.status_code = exception.status
    return response


def shutdown_hook(close_function, name):
    logger.info("Closing %s", name)
    close_function()


def system_profile_spec():
    return current_app.config["SYSTEM_PROFILE_SPEC"]


def _spec_type_to_python_type(type_as_string):
    return SPEC_TYPES_LOOKUP[type_as_string]


def _get_field_filter(field_name, props):
    field_type = None

    if props.get("type"):
        field_type = props["type"]
    elif props.get("$ref"):
        # remove path to get name of custom type
        return props["$ref"].replace("#/$defs/", "")
    else:
        raise Exception("system profile spec is invalid")

    # determine if the field uses a custom filter
    if field_name in custom_filter_fields:
        return field_name

    # determine if the string field supports wildcard queries
    if field_type == "string" and props.get("x-wildcard") is True:
        return "wildcard"

    # if it's an array determine filter type from members
    if field_type == "array":
        return _get_field_filter(None, props["items"])

    return field_type


def process_identity_header(encoded_id_header):
    decoded_id_header = base64.b64decode(encoded_id_header).decode("utf-8")
    id_header_dict = json.loads(decoded_id_header)
    identity = id_header_dict.get("identity", {})
    org_id = identity.get("org_id")
    id_type = identity.get("type")
    access_id = None
    if id_type == "User":
        access_id = identity.get("user", {}).get("user_id")
        if not access_id:
            access_id = identity.get("user", {}).get("username")
    if id_type == "ServiceAccount":
        access_id = identity.get("service_account", {}).get("client_id")
    if id_type == "System":
        access_id = identity.get("system", {}).get("cn")
    if not org_id or not access_id:
        message = f"Invalid identity encountered; id_type={id_type} org_id={org_id}, access_id={access_id}."
        raise Exception(message)  # TODO: Raise more specific exception
    return org_id, access_id


def process_spec(spec):
    system_profile_spec_processed = {}
    for field, props in spec.items():
        field_filter = _get_field_filter(field, props)
        system_profile_spec_processed[field] = {
            "type": _spec_type_to_python_type(props["type"]),  # cast from string to type
            "filter": field_filter,
            "format": props.get("format"),
            "is_array": props.get("type") == "array",
        }

        if "enum" in props:
            system_profile_spec_processed[field]["enum"] = props.get("enum")

        if field_filter in ["object", "operating_system"]:
            # Handle nested object or array of objects in the schema
            item_props = props.get("items", {}).get("properties")
            base_props = props.get("properties", {})

            children_props = item_props or base_props
            if children_props:
                system_profile_spec_processed[field]["children"] = process_spec(children_props)

    return system_profile_spec_processed


def process_system_profile_spec():
    with open(SYSTEM_PROFILE_SPECIFICATION_FILE) as fp:
        return process_spec(yaml.safe_load(fp)["$defs"]["SystemProfile"]["properties"])


def create_app(runtime_environment):
    # This feels like a hack but it is needed.  The logging configuration
    # needs to be setup before the flask app is initialized.
    configure_logging()

    app_config = Config(runtime_environment)
    app_config.log_configuration()
    swagger_options = SwaggerUIOptions(serve_spec=False)
    app = connexion.FlaskApp(
        "inventory",
        specification_dir="./swagger/",
        uri_parser_class=customURIParser,
        swagger_ui_options=swagger_options,
    )

    parser = TranslatingParser(SPECIFICATION_FILE)
    parser.parse()

    sp_spec = process_system_profile_spec()

    for api_url in app_config.api_urls:
        if api_url:
            app.add_api(
                parser.specification,
                arguments={"title": "RestyResolver Example"},
                resolver=RestyResolver("api"),
                validate_responses=True,
                strict_validation=False,
                base_path=api_url,
                validator_map=build_validator_map(system_profile_spec=sp_spec),
            )
            logger.info("Listening on API: %s", api_url)

    flask_app = app.app

    # Add an error handler that will convert our top level exceptions
    # into error responses
    flask_app.register_error_handler(InventoryException, render_exception)

    flask_app.config["SQLALCHEMY_ECHO"] = False
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = app_config.db_uri
    flask_app.config["SQLALCHEMY_ENGINE_OPTIONS['pool_size']"] = app_config.db_pool_size
    flask_app.config["SQLALCHEMY_ENGINE_OPTIONS['pool_timeout']"] = app_config.db_pool_timeout
    flask_app.config["SQLALCHEMY_ENGINE_OPTIONS['pool_pre_ping']"] = True
    flask_app.config["SQLALCHEMY_ENGINE_OPTIONS['connect_args']"] = {
        "options": f"-c statement_timeout={app_config.db_statement_timeout} -c lock_timeout={app_config.db_lock_timeout}"  # noqa
    }

    flask_app.config["INVENTORY_CONFIG"] = app_config
    flask_app.config["SYSTEM_PROFILE_SPEC"] = sp_spec
    flask_app.config["USE_SUBMAN_ID"] = app_config.use_sub_man_id_for_host_id

    init_cache(app_config, app)

    # Configure Unleash (feature flags)
    if not app_config.bypass_unleash and app_config.unleash_token:
        flask_app.config["UNLEASH_APP_NAME"] = "host-inventory-api"
        flask_app.config["UNLEASH_ENVIRONMENT"] = "default"
        flask_app.config["UNLEASH_URL"] = app_config.unleash_url
        flask_app.config["UNLEASH_CUSTOM_HEADERS"] = {"Authorization": app_config.unleash_token}
        flask_app.config["UNLEASH_CUSTOM_STRATEGIES"] = {"schema-strategy": SchemaStrategy}
        flask_app.config["UNLEASH_REFRESH_INTERVAL"] = app_config.unleash_refresh_interval
        if hasattr(app_config, "unleash_cache_directory"):
            flask_app.config["UNLEASH_CACHE_DIRECTORY"] = app_config.unleash_cache_directory
        init_unleash_app(flask_app)
    else:
        unleash_fallback_msg = (
            "Unleash is bypassed by config value."
            if app_config.bypass_unleash
            else "No API token was provided for Unleash server connection."
        )
        unleash_fallback_msg += " Feature flag toggles will default to their fallback values."
        logger.warning(unleash_fallback_msg)

    db.init_app(flask_app)

    if get_flag_value(FLAG_INVENTORY_KESSEL_HOST_MIGRATION): #Note: this won't work if we want to enable the flag while running or otherwise selectively, but it does allow us to completely disable the feature
        init_kessel(app_config, flask_app)

    flask_app.register_blueprint(monitoring_blueprint, url_prefix=app_config.mgmt_url_path_prefix)
    for api_url in app_config.api_urls:
        flask_app.register_blueprint(spec_blueprint, url_prefix=api_url, name=f"{api_url}{spec_blueprint.name}")

    flask_app.register_blueprint(tags_bp)

    @flask_app.before_request
    def set_request_id():
        threadctx.request_id = request.headers.get(REQUEST_ID_HEADER)

    @flask_app.after_request
    def after_request_org_check(response):
        if any(endpoint in request.endpoint for endpoint in ORG_ID_CHECK_ENDPOINTS):
            response = check_org_id(response)
        return response

    if runtime_environment.event_producer_enabled:
        flask_app.event_producer = EventProducer(app_config, app_config.event_topic)
        register_shutdown(flask_app.event_producer.close, "Closing EventProducer")
    else:
        logger.warning(
            "WARNING: The event producer has been disabled.  "
            "The message queue based event notifications have been disabled."
        )

    if runtime_environment.notification_producer_enabled:
        flask_app.notification_event_producer = EventProducer(app_config, app_config.notification_topic)
        register_shutdown(flask_app.notification_event_producer.close, "Closing NotificationEventProducer")
    else:
        logger.warning(
            "WARNING: The event producer has been disabled.  The message queue based notifications have been disabled."
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
        GunicornPrometheusMetrics(
            flask_app,
            defaults_prefix="inventory",
            group_by="url_rule",
            excluded_paths=["^/metrics$", "^/health$", "^/version$", r"^/favicon\.ico$"],
        )

    # initialize metrics to zero
    initialize_metrics(app_config)

    initialize_segmentio()

    return app
