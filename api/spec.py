import json
import os

from flask import Blueprint
from flask import jsonify

CURRENT_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
SPECIFICATION_FILE = os.path.join(CURRENT_DIR, "swagger", "openapi.json")
spec_blueprint = Blueprint("openapispec", __name__)


@spec_blueprint.route("/openapi.json", methods=["GET"])
def openapi():
    openapi_spec = {}
    try:
        with open(SPECIFICATION_FILE) as spec_file:
            openapi_spec = json.load(spec_file)
    except ValueError:
        pass

    return jsonify(openapi_spec)
