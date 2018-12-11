from flask import Blueprint

management = Blueprint("management", __name__)

@management.route("/health", methods=['GET'])
def health():
    return ("", 200)

@management.route("/metrics", methods=['GET'])
def metrics():
    return ("", 200)
