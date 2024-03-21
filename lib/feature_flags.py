from typing import Tuple

from flask_unleash import Unleash
from UnleashClient.strategies import Strategy

from app.logging import get_logger

UNLEASH = Unleash()
logger = get_logger(__name__)

FLAG_INVENTORY_ASSIGNMENT_RULES = "hbi.group-assignment-rules"
FLAG_INVENTORY_CUSTOM_STALENESS = "hbi.custom-staleness"
FLAG_HIDE_EDGE_HOSTS = "hbi.api.hide-edge-by-default"
FLAG_INVENTORY_DISABLE_XJOIN = "hbi.api.disable-xjoin"

FLAG_FALLBACK_VALUES = {
    FLAG_INVENTORY_ASSIGNMENT_RULES: True,
    FLAG_INVENTORY_CUSTOM_STALENESS: True,
    FLAG_HIDE_EDGE_HOSTS: False,
    FLAG_INVENTORY_DISABLE_XJOIN: False,
}


class SchemaStrategy(Strategy):
    def load_provisioning(self) -> list:
        return self.parameters["schema-name"].split(",")

    def apply(self, context) -> bool:
        default_value = False
        if "schema" in context and context["schema"] is not None:
            default_value = context["schema"] in self.parsed_provisioning
        return default_value


def init_unleash_app(app):
    UNLEASH.init_app(app)


# Raise an error if the toggle is not found on the configured Unleash server.
# Without this fallback function, is_enabled just returns False without error.
def custom_fallback(feature_name: str, context: dict) -> bool:
    raise ConnectionError(f"Could not contact Unleash server, or feature toggle {feature_name} not found.")


# Gets a feature flag's value from Unleash, if available.
# Accepts a string with the name of the feature flag.
# Returns a tuple containing the flag's value and whether or not the fallback value was used.
def get_flag_value_and_fallback(flag_name: str, context: dict = {}) -> Tuple[bool, bool]:
    # Get flag name and default to fallback value
    flag_value = FLAG_FALLBACK_VALUES[flag_name]
    using_fallback = True

    # Attempt to get the feature flag via Unleash
    try:
        if UNLEASH.client:
            flag_value = UNLEASH.client.is_enabled(flag_name, context=context, fallback_function=custom_fallback)
            using_fallback = False
    except ConnectionError:
        # Either Unleash wasn't initialized, or there was a connection error.
        # Default to the fallback value.
        logger.warning(
            f"Either could not connect to Unleash server, or feature toggle {flag_name} not found."
            f"Falling back to default value of {flag_value}"
        )
    finally:
        return flag_value, using_fallback


# Gets a feature flag's value from Unleash, if available.
# Accepts a string with the name of the feature flag.
# Returns the value of the feature flag, whether it's the fallback or real value.
def get_flag_value(flag_name: str, context: dict = {}) -> bool:
    return get_flag_value_and_fallback(flag_name, context)[0]
