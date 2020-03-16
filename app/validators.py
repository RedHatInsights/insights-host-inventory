import uuid

import validators
from jsonschema import draft4_format_checker


@draft4_format_checker.checks("uuid")
def verify_uuid_format(uuid_str):
    if not uuid_str:
        return False

    try:
        return uuid.UUID(uuid_str) is not None
    except Exception:
        pass
    return False


@draft4_format_checker.checks("ip_address")
def verify_ip_address_format(ip_address):
    if not ip_address:
        return False

    return validators.ipv4(ip_address) or validators.ipv6(ip_address)


@draft4_format_checker.checks("mac_address")
def verify_mac_address_format(mac_address):
    if not mac_address:
        return False

    return validators.mac_address(mac_address)


def check_empty_keys(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "":
                return False
            if not check_empty_keys(value):
                return False
    elif isinstance(data, list):
        for value in data:
            if not check_empty_keys(value):
                return False

    return True
