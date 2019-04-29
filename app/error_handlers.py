import logging

from flask import jsonify

from flask_api import status
logger = logging.getLogger(__name__)


def marshmallow_validation_error_handler(error):
    logger.exception(error)
    response = jsonify(
        detail=error.messages,
        status=status.HTTP_400_BAD_REQUEST,
        title="Bad Request"
    )
    response.status_code = status.HTTP_400_BAD_REQUEST
    return response


def render_exception(exception):
    response = jsonify(exception.to_json())
    response.status_code = exception.status
    return response
