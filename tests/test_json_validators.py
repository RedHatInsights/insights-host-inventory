import uuid

from api.json_validators import (verify_uuid_format,
                                 verify_ip_address_format,
                                 verify_mac_address_format
                                 )


def test_valid_uuid():
    valid_uuid = str(uuid.uuid4())
    assert verify_uuid_format(valid_uuid) is True


def test_valid_uuid_no_hyphens():
    valid_uuid = uuid.uuid4().hex
    assert verify_uuid_format(valid_uuid) is True


def test_valid_uuid_with_uuid_as_none():
    valid_uuid = None
    assert verify_uuid_format(valid_uuid) is True


def test_invalid_uuid():
    invalid_uuid = "123456"
    assert verify_uuid_format(invalid_uuid) is False


def test_valid_ip_address():
    valid_ip = "192.168.1.1"
    assert verify_ip_address_format(valid_ip) is True


def test_invalid_ip_address():
    invalid_ip_list = ["19216811", "", None]
    for ip in invalid_ip_list:
        assert verify_ip_address_format(ip) is False


def test_valid_mac_address():
    valid_mac_list = ["aa:bb:cc:dd:ee:ff",
                      "AA:22:CC:DD:EE:FF",
                     ]

    for mac in valid_mac_list:
        assert verify_mac_address_format(mac) is True


def test_invalid_mac_address():
    invalid_mac_list = ["aa:bb:cc:dd:ee:xx", "19216811", "", None]

    for mac in invalid_mac_list:
        assert verify_mac_address_format(mac) is False
