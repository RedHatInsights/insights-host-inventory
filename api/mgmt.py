from flask import Blueprint

management = Blueprint("management", __name__)

@management.route("/health", methods=['GET'])
def health():
    return ("health: i'm healthy!", 200)

@management.route("/metrics", methods=['GET'])
def metrics():
    return ("metrics: i'm running very fast!", 200)
