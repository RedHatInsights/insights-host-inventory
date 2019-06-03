#!/usr/bin/env python

import os
import logging

from inventory.app import create_app

config_name = os.getenv('APP_SETTINGS', "development")
application = create_app(config_name)
listen_port = os.getenv('LISTEN_PORT', 8080)

if __name__ == '__main__':
    application.run(host="0.0.0.0", port=listen_port)
