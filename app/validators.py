import ipaddress
import re
import uuid

from dateutil import parser
from jsonschema import draft4_format_checker
from marshmallow.exceptions import ValidationError


@draft4_format_checker.checks("uuid")
def verify_uuid_format_draft4(uuid_str):
    if not uuid_str:
        return False

    try:
        uuid.UUID(uuid_str)
    except Exception:
        return False

    return "-" in uuid_str


def verify_uuid_format(uuid_str):
    if not verify_uuid_format_draft4(uuid_str):
        raise ValidationError("Invalid value.")

    return True


@draft4_format_checker.checks("ip_address")
def verify_ip_address_format(ip_address):
    if not ip_address:
        raise ValidationError("Invalid value.")

    try:
        ipaddress.ip_address(ip_address)
    except ValueError as ve:
        raise ValidationError("Invalid value.") from ve

    return True


@draft4_format_checker.checks("mac_address")
def verify_mac_address_format(mac_address):
    pattern = re.compile(
        r"^([A-Fa-f0-9]{2}[:-]){5}[A-Fa-f0-9]{2}$|"
        r"^([A-Fa-f0-9]{4}[.]){2}[A-Fa-f0-9]{4}$|"
        r"^[A-Fa-f0-9]{12}$|"
        r"^([A-Fa-f0-9]{2}[:-]){19}[A-Fa-f0-9]{2}$|"
        r"^[A-Fa-f0-9]{40}$"
    )

    if not mac_address or not bool(pattern.match(mac_address)):
        raise ValidationError("Invalid value.")

    return True


@draft4_format_checker.checks("date-time")
def is_custom_date(val):
    if val is None:
        return True
    try:
        parser.isoparse(val)
        return True
    except ValueError:
        return False


def check_empty_keys(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "":
                raise ValidationError("Key may not be empty.")
            check_empty_keys(value)
    elif isinstance(data, list):
        for item in data:
            check_empty_keys(item)
    return True


def verify_satellite_id(id_str):
    # satellite_id can either be a UUID or a 10 digit number depending on Sat version

    try:
        verify_uuid_format(id_str)
    except ValidationError as ve:
        if not (id_str and re.match(r"^\d{10}$", id_str)):
            raise ValidationError("Invalid value.") from ve

    return True
