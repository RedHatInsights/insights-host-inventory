from app.common import inventory_config

# This file is being created to reuse the function
# and avoid circular imports


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self

def build_staleness_sys_default(org_id, config=None):
    if not config:
        config = inventory_config()

    return AttrDict(
        {
            "id": "system_default",
            "org_id": org_id,
            "conventional_time_to_stale": config.conventional_time_to_stale_seconds,
            "conventional_time_to_stale_warning": config.conventional_time_to_stale_warning_seconds,
            "conventional_time_to_delete": config.conventional_time_to_delete_seconds,
            "immutable_time_to_stale": config.immutable_time_to_stale_seconds,
            "immutable_time_to_stale_warning": config.immutable_time_to_stale_warning_seconds,
            "immutable_time_to_delete": config.immutable_time_to_delete_seconds,
            "created_on": None,
            "modified_on": None,
        }
    )


# This is required because we do not keep a ORM object that is attached to a session
# leaving in the global scope. Before this serialization,
# it was causing sqlalchemy.orm.exc.DetachedInstanceError
def build_serialized_acc_staleness_obj(staleness):
    return AttrDict(
        {
            "id": str(staleness.id),
            "org_id": staleness.org_id,
            "conventional_time_to_stale": staleness.conventional_time_to_stale,
            "conventional_time_to_stale_warning": staleness.conventional_time_to_stale_warning,
            "conventional_time_to_delete": staleness.conventional_time_to_delete,
            "immutable_time_to_stale": staleness.immutable_time_to_stale,
            "immutable_time_to_stale_warning": staleness.immutable_time_to_stale_warning,
            "immutable_time_to_delete": staleness.immutable_time_to_delete,
            "created_on": staleness.created_on,
            "modified_on": staleness.modified_on,
        }
    )


def get_staleness_timestamps_from_dict(host, staleness_timestamps, staleness) -> dict:
    """Helper function to calculate staleness timestamps based on host type."""
    staleness_type = (
        "immutable"
        if (
            hasattr(host, "system_profile_facts")
            and host.system_profile_facts
            and host.system_profile_facts.get("host_type") == "edge"
        )
        else "conventional"
    )

    return {
        "stale_timestamp": staleness_timestamps.stale_timestamp(
            host.modified_on, staleness[f"{staleness_type}_time_to_stale"]
        ),
        "stale_warning_timestamp": staleness_timestamps.stale_warning_timestamp(
            host.modified_on, staleness[f"{staleness_type}_time_to_stale_warning"]
        ),
        "culled_timestamp": staleness_timestamps.culled_timestamp(
            host.modified_on, staleness[f"{staleness_type}_time_to_delete"]
        ),
    }