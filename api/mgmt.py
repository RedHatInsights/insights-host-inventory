from flask import Blueprint
from flask import jsonify
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry
from prometheus_client import generate_latest
from prometheus_client import multiprocess

from app.common import get_build_version

monitoring_blueprint = Blueprint("monitoring", __name__)


@monitoring_blueprint.route("/health", methods=["GET"])
def health():
    return "", 200


@monitoring_blueprint.route("/metrics", methods=["GET"])
def metrics():
    headers = {"content-type": CONTENT_TYPE_LATEST}
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    prometheus_data = generate_latest(registry)
    return prometheus_data, 200, headers


@monitoring_blueprint.route("/version", methods=["GET"])
def version():
    return jsonify({"version": get_build_version()})
