from typing import Tuple

from flask_unleash import Unleash

UNLEASH = Unleash()
FLAG_INVENTORY_GROUPS = ("hbi.api.inventory-groups", True)


def init_unleash_app(app):
    UNLEASH.init_app(app)


# Raise an error if the toggle is not found on the configured Unleash server.
# Without this fallback function, is_enabled just returns False without error.
def custom_fallback(feature_name: str, context: dict) -> bool:
    raise AttributeError(f"Unleash toggle {feature_name} not found!")


def get_flag_value(feature_flag: Tuple[str, bool]) -> Tuple[bool, bool]:
    try:
        # Attempt to get the feature flag via Unleash
        return UNLEASH.client.is_enabled(feature_flag[0], fallback_function=custom_fallback), False
    except AttributeError:
        # Return the default value if not connected to Unleash
        return feature_flag[1], True
