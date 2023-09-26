from api import api_operation
from api import flask_json_response
from api import metrics
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value_and_fallback


@api_operation
@metrics.api_request_time.time()
def get_inventory_groups_toggle():
    # TODO: Remove once it's no longer useful.
    # This endpoint just exists to make it easier to check the connection to the Unleash server.
    flag_value, using_fallback = get_flag_value_and_fallback(FLAG_INVENTORY_GROUPS)
    json_data = {"flag_value": flag_value, "using_fallback_value": using_fallback}
    return flask_json_response(json_data)
