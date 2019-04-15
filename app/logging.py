import logging
import logging.config
import logstash_formatter
import os

from gunicorn import glogging
from flask import request

from app.auth import current_identity

REQUEST_ID_HEADER = "x-rh-insights-request-id"
UNKNOWN_REQUEST_ID_VALUE = "-1"


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
        # Only enable the contextual filter if not in "testing" mode
        root = logging.getLogger()
        root.addFilter(ContextualFilter())

        # FIXME: Figure out a better way to load the list of modules/submodules
        for logger_name in ("app", "app.models", "api", "api.host"):
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
        log_record.request_id = request.headers.get(REQUEST_ID_HEADER,
                                                    UNKNOWN_REQUEST_ID_VALUE)

        log_record.account_number = current_identity.account_number
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
