from __future__ import annotations

import os

from flask_unleash import Unleash
from UnleashClient.strategies import Strategy

from app.logging import get_logger

UNLEASH = Unleash()
logger = get_logger(__name__)

FLAG_INVENTORY_USE_CACHED_INSIGHTS_CLIENT_SYSTEM = "hbi.api.use-cached-insights-client-system"
FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION = "hbi.api.kessel-workspace-migration"
FLAG_INVENTORY_KESSEL_HOST_MIGRATION = "hbi.api.kessel-host-migration"
FLAG_INVENTORY_API_READ_ONLY = "hbi.api.read-only"
FLAG_INVENTORY_DEDUPLICATION_ELEVATE_SUBMAN_ID = "hbi.deduplication-elevate-subman_id"
FLAG_INVENTORY_KESSEL_PHASE_1 = "hbi.api.kessel-phase-1"
FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS = (
    "hbi.create_last_check_in_update_per_reporter_staleness"
)
FLAG_INVENTORY_FILTER_STALENESS_USING_COLUMNS = "hbi.filter_staleness_using_columns"

ENV_FLAG_LAST_CHECKIN_PER_REPORTER_STALENESS = os.getenv("FF_LAST_CHECKIN", "false").lower() == "true"

FLAG_FALLBACK_VALUES = {
    FLAG_INVENTORY_USE_CACHED_INSIGHTS_CLIENT_SYSTEM: False,
    FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION: False,
    FLAG_INVENTORY_KESSEL_HOST_MIGRATION: False,
    FLAG_INVENTORY_API_READ_ONLY: False,
    FLAG_INVENTORY_KESSEL_PHASE_1: False,
    FLAG_INVENTORY_DEDUPLICATION_ELEVATE_SUBMAN_ID: True,
    FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS: ENV_FLAG_LAST_CHECKIN_PER_REPORTER_STALENESS,
    # Use when all hosts are populated with stale_warning/deletion_timestamps
    FLAG_INVENTORY_FILTER_STALENESS_USING_COLUMNS: False,
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
