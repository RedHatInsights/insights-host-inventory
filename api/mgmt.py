from flask import Blueprint
from prometheus_client import CollectorRegistry, multiprocess, generate_latest, CONTENT_TYPE_LATEST

management = Blueprint("management", __name__)


@management.route("/health", methods=['GET'])
def health():
    return ("", 200)


@management.route("/metrics", methods=['GET'])
def metrics():
    headers = {'content-type': CONTENT_TYPE_LATEST}
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    prometheus_data = generate_latest(registry)
    return prometheus_data, 200, headers
