from iqe.deprecations import deprecator

deprecated = deprecator(plugin_package_name="iqe_host_inventory_plugin")


# API utils

DEPRECATE_ASYNC_GET_MULTIPLE_HOSTS = deprecated(
    "async_get_multiple_hosts_by_insights_id will be removed.",
    "app.host_inventory.apis.hosts.async_wait_for_created_by_insights_ids",
    "v25.3.1.0",
)


# Kafka fixtures

DEPRECATE_MQ_FIXTURES = deprecated(
    "mq_fixtures.py will be removed.",
    "kafka_fixtures.py",
    "v25.6.1.0",
)

# Kafka interactions

DEPRECATE_MAKE_HOST_EVENTS = deprecated(
    "make_host_events will be removed.",
    "create_host_events",
    "v25.6.1.0",
)

DEPRECATE_PRODUCE_HOST_UPDATE_MESSAGES = deprecated(
    "produce_host_update_messages will be removed.",
    "produce_host_create_messages",
    "v25.6.1.0",
)

DEPRECATE_MAKE_HOST_DATA = deprecated(
    "make_host_data will be removed.",
    "create_host_data",
    "v25.6.1.0",
)


# Group fixtures

DEPRECATE_PRIMARY_GROUPS_CLEANUP_FUNCTION = deprecated(
    "hbi_primary_groups_cleanup_function will be removed.",
    "per-plugin autouse cleanup fixtures, see iqe_host_inventory/tests/conftest.py",
    "v25.6.1.0",
)
