from flask import Blueprint
from prometheus_client import CollectorRegistry, multiprocess, generate_latest, CONTENT_TYPE_LATEST

monitoring_blueprint = Blueprint("monitoring", __name__)


@monitoring_blueprint.route("/health", methods=['GET'])
def health():
    return "", 200


@monitoring_blueprint.route("/metrics", methods=['GET'])
def metrics():
    headers = {'content-type': CONTENT_TYPE_LATEST}
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    prometheus_data = generate_latest(registry)
    return prometheus_data, 200, headers
