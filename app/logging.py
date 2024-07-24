import logging.config
import os
from logging import NullHandler
from threading import local

import logstash_formatter
import watchtower
from boto3.session import Session
from gunicorn import glogging
from yaml import safe_load

OPENSHIFT_ENVIRONMENT_NAME_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
DEFAULT_AWS_LOGGING_NAMESPACE = "inventory-dev"
DEFAULT_LOGGING_CONFIG_FILE = "logconfig.yaml"
LOGGER_NAME = "inventory"

threadctx = local()


def configure_logging():
    log_config_file = os.getenv("INVENTORY_LOGGING_CONFIG_FILE", DEFAULT_LOGGING_CONFIG_FILE)
    with open(log_config_file) as log_config_file:
        logconfig_dict = safe_load(log_config_file)
        logconfig_dict["disable_existing_loggers"] = False

    logging.config.dictConfig(logconfig_dict)
    logger = logging.getLogger(LOGGER_NAME)
    log_level = os.getenv("INVENTORY_LOG_LEVEL", "INFO").upper()
    logger.setLevel(log_level)

    # Allows for the log level of certain loggers to be redefined with an env variable
    # e.g. SQLALCHEMY_ENGINE_LOG_LEVEL=DEBUG
    for component in ("sqlalchemy.engine", "urllib3"):
        env_key = component.replace(".", "_").upper()
        level = os.getenv(f"{env_key}_LOG_LEVEL")
        if level:
            logging.getLogger(component).setLevel(level.upper())


def clowder_config():
    import app_common_python

    cfg = app_common_python.LoadedConfig

    if cfg.logging:
        cw = cfg.logging.cloudwatch
        return cw.accessKeyId, cw.secretAccessKey, cw.region, cw.logGroup, False
    else:
        return None, None, None, None, None


def non_clowder_config():
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", None)
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", None)
    aws_region_name = os.getenv("AWS_REGION_NAME", None)
    aws_log_group = os.getenv("AWS_LOG_GROUP", "platform")
    create_log_group = str(os.getenv("AWS_CREATE_LOG_GROUP")).lower() == "true"
    return aws_access_key_id, aws_secret_access_key, aws_region_name, aws_log_group, create_log_group


def cloudwatch_handler():
    if os.environ.get("CLOWDER_ENABLED", "").lower() == "true":
        f = clowder_config
    else:
        f = non_clowder_config

    aws_access_key_id, aws_secret_access_key, aws_region_name, aws_log_group, create_log_group = f()

    if all((aws_access_key_id, aws_secret_access_key, aws_region_name)):
        aws_log_stream = os.getenv("AWS_LOG_STREAM", _get_hostname())
        print(f"Configuring watchtower logging (log_group_name={aws_log_group}, log_stream_name={aws_log_stream})")
        boto3_session = Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region_name,
        )
        boto3_client = boto3_session.client("logs")
        return watchtower.CloudWatchLogHandler(
            boto3_client=boto3_client,
            log_group_name=aws_log_group,
            log_stream_name=aws_log_stream,
            create_log_group=create_log_group,
        )
    else:
        print("Unable to configure watchtower logging.  Please verify watchtower logging configuration!")
        return NullHandler()


def _get_hostname():
    return os.uname().nodename


class ContextualFilter(logging.Filter):
    """
    This filter gets the request_id from the flask request
    and adds it to each log record.  This way we do not have
    to explicitly retrieve/pass around the request id for each
    log message.
    """

    def filter(self, log_record):
        try:
            log_record.request_id = threadctx.request_id
        except Exception:
            # TODO: need to decide what to do when you log outside the context
            # of a request
            log_record.request_id = None

        try:
            log_record.account_number = threadctx.account_number
        except Exception:
            # TODO: need to decide what to do when you log outside the context
            # of a request
            log_record.account_number = None

        try:
            log_record.org_id = threadctx.org_id
        except Exception:
            # TODO: need to decide what to do when you log outside the context
            # of a request
            log_record.org_id = None

        return True


class InventoryGunicornLogger(glogging.Logger):
    """
    The logger used by the gunicorn arbiter ignores configuration from
    the logconfig.ini/--log-config.  This class is required so that the
    log messages emmitted by the arbiter are routed through the
    logstash formatter.  If they do not get routed through the logstash
    formatter, then kibana appears to ignore them.  This could cause
    us to lose "WORKER TIMEOUT" error messages, etc.
    """

    def setup(self, cfg):
        super().setup(cfg)

        self._set_handler(self.error_log, cfg.errorlog, logstash_formatter.LogstashFormatterV1())


def get_logger(name):
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
