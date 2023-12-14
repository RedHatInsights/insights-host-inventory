import os

from flask import current_app


def get_build_version():
    return os.getenv("OPENSHIFT_BUILD_COMMIT", "Unknown")


def inventory_config():
    return current_app.config["INVENTORY_CONFIG"]
