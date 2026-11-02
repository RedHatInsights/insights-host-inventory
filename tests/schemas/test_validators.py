import pytest
from marshmallow.exceptions import ValidationError

from app.validators import verify_ip_address_format
from app.validators import verify_mac_address_format
from app.validators import verify_satellite_id
from app.validators import verify_uuid_format


# A valid UUID for canonical_facts must include hyphens.
def test_valid_uuid():
    verify_uuid_format("4a8fb994-57fe-4dbb-ad2a-9e922560b6c1")


@pytest.mark.parametrize(
    "uuid",
    [
        "123456",
        "",
        "4a8fb994-57fe-4dbb-ad2a-9e922560b6c1DEADBEEF",
        "4a8fb994a57feb4dbbcad2ac9e922560b6c1DEADBEEF",
        "4a8fb994a57feb4dbbcad2ac9e922560b6c1DEADBEEFxxxxxx",
        "4a8fb99457fe4dbbad2a9e922560b6c1DEADBEEF",
        "4a8fb99457fe4dbbad2a9e922560b6c1",
        None,
    ],
)
def test_invalid_uuid(uuid):
    with pytest.raises(ValidationError):
        verify_uuid_format(uuid)


@pytest.mark.parametrize("satellite_id", ["4a8fb994-57fe-4dbb-ad2a-9e922560b6c1", "1000056432"])
def test_valid_satellite_id(satellite_id):
    verify_satellite_id(satellite_id)


@pytest.mark.parametrize(
    "satellite_id",
    [
        "123456789",
        "",
        "4a8fb994-57fe-4dbb-ad2a-9e922560b6c1DEADBEEF",
        "4a8fb99457fe4dbbad2a9e922560b6c1DEADBEEF",
        None,
    ],
)
def test_invalid_satellite_id(satellite_id):
    with pytest.raises(ValidationError):
        verify_satellite_id(satellite_id)


@pytest.mark.parametrize("ip", ["192.168.1.1", "2001:0db8:85a3:0000:0000:8a2e:0370:7334", "0:0:0:0:0:0:0:1"])
def test_valid_ip_address(ip):
    verify_ip_address_format(ip)


@pytest.mark.parametrize("ip", ["19216811", "", "K00L:0:0:0:0:0:0:1", None])
def test_invalid_ip_address(ip):
    with pytest.raises(ValidationError):
        verify_ip_address_format(ip)


@pytest.mark.parametrize("mac", ["aa:bb:cc:dd:ee:ff", "AA:22:CC:DD:EE:FF"])
def test_valid_mac_address(mac):
    verify_mac_address_format(mac)


@pytest.mark.parametrize("mac", ["aa:bb:cc:dd:ee:xx", "19216811", "", None])
def test_invalid_mac_address(mac):
    with pytest.raises(ValidationError):
        verify_mac_address_format(mac)
