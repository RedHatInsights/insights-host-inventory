import logging.config
import os
from threading import local

import logstash_formatter
import watchtower
from boto3.session import Session
from gunicorn import glogging

OPENSHIFT_ENVIRONMENT_NAME_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
DEFAULT_AWS_LOGGING_NAMESPACE = "inventory-dev"
LOGGER_NAME = "inventory"
LOGGER_PREFIX = "inventory."

threadctx = local()

# cloudwatch_handler = None


def configure_logging(config_name):
    env_var_name = "INVENTORY_LOGGING_CONFIG_FILE"
    log_config_file = os.getenv(env_var_name, "logconfig.ini")
    if log_config_file is not None:
        # The logging module throws an odd error (KeyError) if the
        # config file is not found.  Hopefully, this makes it more clear.
        try:
            fh = open(log_config_file)
            fh.close()
        except FileNotFoundError:
            print(
                f"Error reading the logging configuration file.  Verify the {env_var_name} environment variable is "
                "set correctly. Aborting..."
            )
            raise

        logging.config.fileConfig(fname=log_config_file)

    logger = logging.getLogger(LOGGER_NAME)
    log_level = os.getenv("INVENTORY_LOG_LEVEL", "INFO").upper()
    logger.setLevel(log_level)

    if config_name != "testing":
        _configure_watchtower_logging_handler(logger)
        _configure_contextual_logging_filter(logger)


def _configure_watchtower_logging_handler(logger):
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", None)
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", None)
    aws_region_name = os.getenv("AWS_REGION_NAME", None)
    aws_log_group = os.getenv("AWS_LOG_GROUP", "platform")
    aws_stream_name = os.getenv("AWS_LOG_STREAM", _get_hostname())  # default to hostname
    create_log_group = str(os.getenv("AWS_CREATE_LOG_GROUP")).lower() == "true"

    if all([aws_access_key_id, aws_secret_access_key, aws_region_name, aws_log_group, aws_stream_name]):
        print(f"Configuring watchtower logging (log_group={aws_log_group}, stream_name={aws_stream_name})")
        global cloudwatch_handler
        cloudwatch_handler = _get_cloudwatch_handler(
            aws_access_key_id, aws_secret_access_key, aws_region_name, aws_log_group, aws_stream_name, create_log_group
        )

        handler = _get_cloudwatch_handler(aws_access_key_id, aws_secret_access_key, aws_region_name, aws_log_group, aws_stream_name, create_log_group)
        # logger = logger.addHandler(handler)
        logger.addHandler(handler)

    # if all([aws_access_key_id, aws_secret_access_key, aws_region_name, aws_log_group, aws_stream_name]):
    #     print(f"Configuring watchtower logging (log_group={aws_log_group}, stream_name={aws_stream_name})")
    #     boto3_session = Session(
    #         aws_access_key_id=aws_access_key_id,
    #         aws_secret_access_key=aws_secret_access_key,
    #         region_name=aws_region_name,
    #     )
        
    else:
        print("Unable to configure watchtower logging.  Please verify watchtower logging configuration!")


def _get_cloudwatch_handler(aws_access_key_id, aws_secret_access_key, aws_region_name, aws_log_group, aws_stream_name, create_log_group):
    # global session_boto3
    # group = os.getenv("AWS_LOG_GROUP", "platform")
    # stream = os.getenv("AWS_LOG_STREAM", _get_hostname())
    # create_log_group = str(os.getenv("AWS_CREATE_LOG_GROUP")).lower() == "true"
    # handler = watchtower.CloudWatchLogHandler(
    #     boto3_session=session_boto3, log_group=group, stream_name=stream, create_log_group=create_log_group
    # )
    # handler.setFormatter(logstash_formatter.LogstashFormatterV1())
    # return handler
    print(f"Configuring watchtower logging (log_group={aws_log_group}, stream_name={aws_stream_name})")
    boto3_session = Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=aws_region_name,
    )
    handler = watchtower.CloudWatchLogHandler(
        boto3_session=boto3_session,
        log_group=aws_log_group,
        stream_name=aws_stream_name,
        create_log_group=create_log_group
    )
    handler.setFormatter(logstash_formatter.LogstashFormatterV1())
    return handler

def _get_hostname():
    return os.uname()[1]


def _configure_contextual_logging_filter(logger):
    # Only enable the contextual filter if not in "testing" mode
    root = logging.getLogger()
    root.addFilter(ContextualFilter())


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
    # log_level = os.getenv("INVENTORY_LOG_LEVEL", "INFO").upper()
    # logger = logging.getLogger(LOGGER_PREFIX + name)
    # logger.addFilter(ContextualFilter())

    # global cloudwatch_handler
    # if cloudwatch_handler:
    #     logger.addHandler(cloudwatch_handler)
    # # if session_boto3 is not None:
    # #     logger.addHandler(_get_cloudwatch_handler())

    # logger.setLevel(log_level)
    # return logger
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
