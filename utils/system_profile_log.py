from app.common import inventory_config
from app.models import Host


def extract_sp_to_log(sp_data: dict) -> dict:
    return {k: sp_data[k] for k in inventory_config().sp_fields_to_log if k in sp_data}


def extract_host_model_sp_to_log(host: Host) -> dict:
    return extract_sp_to_log(host.system_profile_facts)


def extract_host_dict_sp_to_log(host_data: dict) -> dict:
    if "system_profile" in host_data:
        return extract_sp_to_log(host_data["system_profile"])
    else:
        return {}
