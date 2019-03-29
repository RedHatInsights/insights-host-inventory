import logging
import logging.config
import os

from flask import request

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
        return True



