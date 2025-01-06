from app.common import inventory_config
from app.models import Host


def _extract_sp_to_log(sp_data: dict) -> dict:
    if not sp_data:
        return {}
    else:
        return {k: sp_data[k] for k in inventory_config().sp_fields_to_log if k in sp_data}


def extract_host_model_sp_to_log(host: Host) -> dict:
    return _extract_sp_to_log(host.system_profile_facts)


def extract_host_dict_sp_to_log(host_data: dict) -> dict:
    return _extract_sp_to_log(host_data.get("system_profile", {}))
