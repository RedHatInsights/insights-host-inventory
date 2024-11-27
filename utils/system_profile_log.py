from app.common import inventory_config
from app.models import Host


def extract_sp_to_log(host_data):
    sys_profile_fields = inventory_config().build_sys_profile_fields()
    if isinstance(host_data, dict):
        sp_fields_to_log = {
            k: host_data["system_profile"][k] for k in sys_profile_fields if k in host_data["system_profile"]
        }
    elif isinstance(host_data, Host):
        sp_fields_to_log = {
            k: host_data.system_profile_facts[k] for k in sys_profile_fields if k in host_data.system_profile_facts
        }
    else:
        sp_fields_to_log = {}

    return sp_fields_to_log
