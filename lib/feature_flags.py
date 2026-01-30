from __future__ import annotations

from flask_unleash import Unleash

from app.logging import get_logger

UNLEASH = Unleash()
logger = get_logger(__name__)

FLAG_INVENTORY_API_READ_ONLY = "hbi.api.read-only"
FLAG_INVENTORY_KESSEL_PHASE_1 = "hbi.api.kessel-phase-1"
FLAG_INVENTORY_USE_NEW_SYSTEM_PROFILE_TABLES = "hbi.use_new_system_profile_tables"
FLAG_INVENTORY_REJECT_RHSM_PAYLOADS = "hbi.api.reject-rhsm-payloads"
FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY = "hbi.workloads_fields_backward_compatibility"
FLAG_INVENTORY_KESSEL_GROUPS = "hbi.api.kessel-groups"
FLAG_INVENTORY_NEW_STALE_TIMESTAMP_PER_REPORTER_FILTER = "hbi.api.new-stale-timestamp-per-reporter-filter"


FLAG_FALLBACK_VALUES = {
    FLAG_INVENTORY_API_READ_ONLY: False,
    FLAG_INVENTORY_KESSEL_PHASE_1: False,
    # Use when all hosts are populated with stale_warning/deletion_timestamps
    FLAG_INVENTORY_USE_NEW_SYSTEM_PROFILE_TABLES: False,
    FLAG_INVENTORY_REJECT_RHSM_PAYLOADS: False,
    FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY: True,
    FLAG_INVENTORY_KESSEL_GROUPS: False,
    FLAG_INVENTORY_NEW_STALE_TIMESTAMP_PER_REPORTER_FILTER: False,
}


class SchemaStrategy:
    """
    Custom strategy for unleashclient 6.x+
    In version 6.x, custom strategies must implement an apply method
    that takes two parameters: parameters (dict) and context (dict)
    """

    def apply(self, parameters: dict, context: dict) -> bool:
        """
        Evaluate the strategy based on parameters and context.

        Args:
            parameters: Strategy parameters from Unleash (e.g., {"schema-name": "schema1,schema2"})
            context: Context from the application (e.g., {"schema": "schema1"})

        Returns:
            bool: True if the strategy condition is met, False otherwise
        """
        default_value = False
        if "schema" in context and context["schema"] is not None:
            # Parse schema names from parameters
            schema_names = parameters.get("schema-name", "").split(",")
            default_value = context["schema"] in schema_names
        return default_value


def init_unleash_app(app):
    UNLEASH.init_app(app)


# Raise an error if the toggle is not found on the configured Unleash server.
# Without this fallback function, is_enabled just returns False without error.
def custom_fallback(feature_name: str, context: dict) -> bool:  # noqa: ARG001, required by UnleashClient
    raise ConnectionError(f"Could not contact Unleash server, or feature toggle {feature_name} not found.")


# Gets a feature flag's value from Unleash, if available.
# Accepts a string with the name of the feature flag.
# Returns a tuple containing the flag's value and whether or not the fallback value was used.
def get_flag_value_and_fallback(flag_name: str, context: dict | None = None) -> tuple[bool, bool]:
    if context is None:
        context = {}

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

    return flag_value, using_fallback


# Gets a feature flag's value from Unleash, if available.
# Accepts a string with the name of the feature flag.
# Returns the value of the feature flag, whether it's the fallback or real value.
def get_flag_value(flag_name: str, context: dict | None = None) -> bool:
    if context is None:
        context = {}

    return get_flag_value_and_fallback(flag_name, context)[0]
