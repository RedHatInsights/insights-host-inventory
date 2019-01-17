import uuid
import validators

from jsonschema import draft4_format_checker


@draft4_format_checker.checks('uuid')
def verify_uuid_format(uuid_str):
    if uuid_str is None:
        # None/null checking is handled by Connexion before this format check
        # For now, allow UUID fields to be None at this level
        return True

    try:
        uuid.UUID(uuid_str, version=4)
        return True
    except:
        pass
    return False


@draft4_format_checker.checks('ip_address')
def verify_ip_address_format(ip_address):
    try:
        if(validators.ip_address.ipv4(ip_address) or
                validators.ip_address.ipv6(ip_address)):
            return True
    except:
        pass
    return False


@draft4_format_checker.checks('mac_address')
def verify_mac_address_format(mac_address):
    try:
        if validators.mac_address(mac_address):
            return True
    except:
        pass
    return False
