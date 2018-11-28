#!/usr/bin/env python

import os
import logging

from app import create_app

config_name = os.getenv('APP_SETTINGS', "development")
connexion_app = create_app(config_name)
flask_app = connexion_app.app
listen_port = os.getenv('LISTEN_PORT', 8080)

if __name__ == '__main__':
    flask_app.run(host="0.0.0.0", port=listen_port)
else:
    # Running within gunicorn...tie the flask_app logging
    # into the gunicorn loggging
    gunicorn_logger = logging.getLogger("gunicorn.error")
    flask_app.logger.handlers = gunicorn_logger.handlers
    flask_app.logger.setLevel(gunicorn_logger.level)
