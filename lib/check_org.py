from flask import Response
from flask import current_app
from flask import request
from werkzeug.exceptions import Forbidden

from app.auth import get_current_identity
from app.logging import get_logger

logger = get_logger(__name__)


def check_org_id(result):
    current_identity = get_current_identity()
    if isinstance(result, Response):
        data = result.get_json()
    elif isinstance(result, tuple):
        data = result[0]
    else:
        data = result
    if isinstance(data, dict):
        message = f"Response contained data for another org_id. Path={request.path}, parameters={request.args}."
        if "org_id" in data and data["org_id"] != current_identity.org_id:
            logger.error(message)
            result = current_app.make_response(current_app.handle_user_exception(Forbidden()))
        if "results" in data:
            results_array = data.get("results", [])
            for system in results_array:
                org_id = system.get("org_id")
                if org_id and (org_id != current_identity.org_id):
                    logger.error(message)
                    result = current_app.make_response(current_app.handle_user_exception(Forbidden()))
    return result
