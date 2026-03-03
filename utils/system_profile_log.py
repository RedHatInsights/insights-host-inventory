from app.common import inventory_config
from app.models import Host
from app.models.system_profile_transformer import DYNAMIC_FIELDS
from app.models.system_profile_transformer import STATIC_FIELDS


def _extract_sp_to_log(sp_data: dict) -> dict:
    if not sp_data:
        return {}
    else:
        return {k: sp_data[k] for k in inventory_config().sp_fields_to_log if k in sp_data}


def _build_sp_dict_from_normalized(host: Host) -> dict:
    """Build a system profile dict from the normalized tables for logging."""
    sp_data = {}

    # Extract fields from static system profile
    if host.static_system_profile:
        for field in STATIC_FIELDS:
            value = getattr(host.static_system_profile, field, None)
            if value is not None:
                sp_data[field] = value

    # Extract fields from dynamic system profile
    if host.dynamic_system_profile:
        for field in DYNAMIC_FIELDS:
            value = getattr(host.dynamic_system_profile, field, None)
            if value is not None:
                sp_data[field] = value

    return sp_data


def extract_host_model_sp_to_log(host: Host) -> dict:
    sp_data = _build_sp_dict_from_normalized(host)
    return _extract_sp_to_log(sp_data)


def extract_host_dict_sp_to_log(host_data: dict) -> dict:
    return _extract_sp_to_log(host_data.get("system_profile", {}))
