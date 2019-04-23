from threading import local
import logging
import logging.config
import logstash_formatter
import os
import watchtower

from boto3.session import Session
from gunicorn import glogging

from app.auth import current_identity

OPENSHIFT_ENVIRONMENT_NAME_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
DEFAULT_AWS_LOGGING_NAMESPACE = "inventory-dev"
threadctx = local()

modules = ("app", "app.models", "api", "api.host", "tasks")


def configure_logging(config_name):
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

    if config_name != "testing":
        _configure_watchtower_logging_handler()
        _configure_contextual_logging_filter()


def _configure_watchtower_logging_handler():
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", None)
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", None)
    aws_region_name = os.getenv("AWS_REGION_NAME", None)
    log_group = "platform"
    stream_name = _get_aws_logging_stream_name(OPENSHIFT_ENVIRONMENT_NAME_FILE)
    log_level = os.getenv("INVENTORY_LOG_LEVEL", "WARNING").upper()

    if all([aws_access_key_id, aws_secret_access_key,
            aws_region_name, stream_name]):
        print(f"Configuring watchtower logging (log_group={log_group}, stream_name={stream_name})")
        boto3_session = Session(aws_access_key_id=aws_access_key_id,
                                aws_secret_access_key=aws_secret_access_key,
                                region_name=aws_region_name)

        root = logging.getLogger()
        handler = watchtower.CloudWatchLogHandler(boto3_session=boto3_session,
                                                  log_group=log_group,
                                                  stream_name=stream_name)
        handler.setFormatter(logstash_formatter.LogstashFormatterV1())
        root.addHandler(handler)

        for logger_name in modules:
            app_logger = logging.getLogger(logger_name)
            app_logger.setLevel(log_level)

    else:
        print("Unable to configure watchtower logging.  Please "
              "verify watchtower logging configuration!")


def _get_aws_logging_stream_name(namespace_filename):
    try:
        with open(namespace_filename) as namespace_fh:
            return namespace_fh.read()
    except FileNotFoundError:
        namespace = DEFAULT_AWS_LOGGING_NAMESPACE
        print(f"Error reading the OpenShift namepsace file.  "
              f"Using {namespace} as aws logging stream name")
        return namespace


def _configure_contextual_logging_filter():
    # Only enable the contextual filter if not in "testing" mode
    root = logging.getLogger()
    root.addFilter(ContextualFilter())

    # FIXME: Figure out a better way to load the list of modules/submodules
    for logger_name in modules:
        app_logger = logging.getLogger(logger_name)
        app_logger.addFilter(ContextualFilter())


class ContextualFilter(logging.Filter):
    """
    This filter gets the request_id from the flask reqeust
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
            log_record.account_number = current_identity.account_number
        except Exception:
            # TODO: need to decide what to do when you log outside the context
            # of a request
            log_record.account_number = None

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

        self._set_handler(self.error_log,
                          cfg.errorlog,
                          logstash_formatter.LogstashFormatterV1())
