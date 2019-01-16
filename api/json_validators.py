import uuid
import validators

from jsonschema import draft4_format_checker


@draft4_format_checker.checks('uuid')
def verify_uuid_format(uuid_str):
    if uuid_str is None:
        # UUID fields are nullable...currently.
        # FIXME:  I'm not really happy with this.  It would be nice to
        # look at the "x-nullable" flag in the schema.
        return True

    try:
        uuid.UUID(uuid_str, version=4)
    except:
        return False
    return True


@draft4_format_checker.checks('ip_address')
def verify_ip_address_format(ip_address):
    if(validators.ip_address.ipv4(ip_address) or
            validators.ip_address.ipv6(ip_address)):
        return True
    else:
        return False


@draft4_format_checker.checks('mac_address')
def verify_mac_address_format(mac_address):
    if validators.mac_address(mac_address):
        return True
    else:
        return False
