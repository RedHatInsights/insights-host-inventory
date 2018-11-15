#!/usr/bin/env python

import os
import logging

from app import create_app

config_name = os.getenv('APP_SETTINGS', "development")
application = create_app(config_name)
listen_port = os.getenv('LISTEN_PORT', 8080)

if __name__ == '__main__':
    application.run(host="0.0.0.0", port=listen_port)
else:
    # Running within gunicorn...tie the flask_app logging
    # into the gunicorn loggging
    gunicorn_logger = logging.getLogger("gunicorn.error")
    application.logger.handlers = gunicorn_logger.handlers
    application.logger.setLevel(gunicorn_logger.level)
