from typing import Tuple

from flask_unleash import Unleash

from app.logging import get_logger

UNLEASH = Unleash()
logger = get_logger(__name__)

FLAG_INVENTORY_GROUPS = ("hbi.api.inventory-groups", True)


def init_unleash_app(app):
    UNLEASH.init_app(app)


# Raise an error if the toggle is not found on the configured Unleash server.
# Without this fallback function, is_enabled just returns False without error.
def custom_fallback(feature_name: str, context: dict) -> bool:
    raise ConnectionError(f"Could not contact Unleash server, or feature toggle {feature_name} not found!")


# Gets a feature flag's value from Unleash, if available.
# Accepts a feature flag in the format:
#   (<feature_flag_name>, <fallback_value>)
# Returns a tuple containing the flag's value and whether or not the fallback value was used.
def get_flag_value(feature_flag: Tuple[str, bool]) -> Tuple[bool, bool]:
    # Set defaults
    flag_value = feature_flag[1]
    using_fallback = True

    # Attempt to get the feature flag via Unleash
    try:
        if hasattr(UNLEASH, "client"):
            flag_value = UNLEASH.client.is_enabled(feature_flag[0], fallback_function=custom_fallback)
            using_fallback = False
    except ConnectionError as ce:
        logger.warning(ce)
    finally:
        # Either Unleash wasn't initialized, or there was a connection error.
        # Use the fallback value.
        return flag_value, using_fallback
