import uuid

from api.json_validators import verify_uuid_format


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
