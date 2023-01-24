from api import api_operation
from api import flask_json_response
from api import metrics
from app import Permission
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.middleware import rbac


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_test_toggle():
    # TODO: Remove once it's no longer useful.
    # This endpoint just exists to make it easier to check the connection to the Unleash server.
    flag_value, using_default = get_flag_value(FLAG_INVENTORY_GROUPS)
    json_data = {"flag_value": flag_value, "using_fallback_value": using_default}
    return flask_json_response(json_data)
