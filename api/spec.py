import json

from flask import Blueprint
from flask import jsonify

spec_blueprint = Blueprint("openapispec", __name__)


@spec_blueprint.route("/openapi.json", methods=["GET"])
def openapi():
    openapi_spec = {}
    try:
        openapi_spec = json.loads("../swagger/openapi.json")
    except ValueError:
        pass

    return jsonify(openapi_spec)
