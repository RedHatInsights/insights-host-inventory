from flask_api import status

from api import api_operation
from api import flask_json_response
from api import metrics
from app.logging import get_logger

logger = get_logger(__name__)


def _get_return_data():
    # This is mock result, will be changed during each endpoint task work
    return {
        "id": "1ba078bb-8461-474c-8498-1e50a1975cfb",
        "account_id": "0123456789",
        "org_id": "123",
        "conventional_staleness_delta": "1",
        "conventional_stale_warning_delta": "7",
        "conventional_culling_delta": "14",
        "immutable_staleness_delta": "2",
        "immutable_stale_warning_delta": "120",
        "immutable_culling_delta": "180",
        "created_at": "2023-07-28T14:32:16.353082",
        "updated_at": "2023-07-28T14:32:16.353082",
    }


@api_operation
@metrics.api_request_time.time()
def get_staleness():
    return flask_json_response(_get_return_data(), status.HTTP_200_OK)


@api_operation
@metrics.api_request_time.time()
def create_staleness():
    return flask_json_response(_get_return_data(), status.HTTP_201_CREATED)


@api_operation
@metrics.api_request_time.time()
def update_staleness():
    return flask_json_response(_get_return_data(), status.HTTP_200_OK)


@api_operation
@metrics.api_request_time.time()
def reset_staleness():
    return flask_json_response(_get_return_data(), status.HTTP_200_OK)
