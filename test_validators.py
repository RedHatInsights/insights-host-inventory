import pytest

from app.validators import verify_ip_address_format
from app.validators import verify_mac_address_format
from app.validators import verify_uuid_format


@pytest.mark.parametrize(
    "uuid", ["4a8fb994-57fe-4dbb-ad2a-9e922560b6c1", "4a8fb99457fe4dbbad2a9e922560b6c1"]
)
def test_valid_uuid(uuid):
    assert verify_uuid_format(uuid) is True


@pytest.mark.parametrize(
    "uuid",
    [
        "123456",
        "",
        "4a8fb994-57fe-4dbb-ad2a-9e922560b6c1DEADBEEF",
        "4a8fb99457fe4dbbad2a9e922560b6c1DEADBEEF",
        None,
    ],
)
def test_invalid_uuid(uuid):
    assert not verify_uuid_format(uuid)


@pytest.mark.parametrize(
    "ip", ["192.168.1.1", "2001:0db8:85a3:0000:0000:8a2e:0370:7334", "0:0:0:0:0:0:0:1"]
)
def test_valid_ip_address(ip):
    assert verify_ip_address_format(ip) is True


@pytest.mark.parametrize("ip", ["19216811", "", "K00L:0:0:0:0:0:0:1", None])
def test_invalid_ip_address(ip):
    assert not verify_ip_address_format(ip)


@pytest.mark.parametrize("mac", ["aa:bb:cc:dd:ee:ff", "AA:22:CC:DD:EE:FF"])
def test_valid_mac_address(mac):
    assert verify_mac_address_format(mac) is True


@pytest.mark.parametrize("mac", ["aa:bb:cc:dd:ee:xx", "19216811", "", None])
def test_invalid_mac_address(mac):
    assert not verify_mac_address_format(mac)
