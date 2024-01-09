import copy

import pytest

from app.auth.identity import AuthType
from app.auth.identity import CertType
from app.auth.identity import IdentitySchema
from app.auth.identity import IdentityType
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


def identity_test_common(identity):
    result = IdentitySchema().load(identity)
    assert "type" in result
    assert result.get("type") in IdentityType.__members__.values()
    assert "org_id" in result
    org_id_len = len(result.get("org_id"))
    assert org_id_len > 0 and org_id_len <= 36

    if "auth_type" in result:
        assert result.get("auth_type") in AuthType.__members__.values()

    if "account_number" in result:
        account_number_len = len(result.get("account_number"))
        assert account_number_len >= 0 and org_id_len <= 36

    if result.get("type") == IdentityType.USER:
        assert "user" in result
        assert type(result.get("user")) is dict
    elif result.get("type") == IdentityType.SYSTEM:
        assert "system" in result
        system = result.get("system")
        assert type(system) is dict
        assert "cert_type" in system
        assert system.get("cert_type") in CertType.__members__.values()
        assert "cn" in system
    else:  # IdentityType.SERVICE_ACCOUNT
        assert "service_account" in result
        service_acc = result.get("service_account")
        assert type(service_acc) is dict
        assert "client_id" in service_acc
        assert "username" in service_acc


@pytest.mark.parametrize("identity", (USER_IDENTITY, SYSTEM_IDENTITY, SERVICE_ACCOUNT_IDENTITY))
def test_validate_valid_identity_schema(identity):
    identity_test_common(identity)


@pytest.mark.parametrize("remove_acct_number", [True, False])
def test_validate_valid_user_identity_schema(remove_acct_number):
    identity = copy.deepcopy(USER_IDENTITY)
    if remove_acct_number:
        identity.pop("account_number")

    result = IdentitySchema().load(identity)

    if "user" in result:
        assert type(result.get("user")) is dict


def test_validate_valid_system_identity_schema():
    identity_test_common(SYSTEM_IDENTITY)


def test_validate_valid_service_account_identity_schema():
    identity_test_common(SERVICE_ACCOUNT_IDENTITY)


@pytest.mark.parametrize("required", ("type", "auth_type", "org_id"))
def test_identity_missing_required(required):
    # Test missing values
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    bad_identity.pop(required, None)
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)

    # Test blank values
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    bad_identity[required] = ""
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)


def test_system_identity_missing_system():
    # Test blank system
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    bad_identity["system"] = {}
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)

    # Test missing system
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    bad_identity.pop("system", None)
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)


@pytest.mark.parametrize("required", ("cert_type", "cn"))
def test_system_identity_missing_required(required):
    # Test blank values
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    assert "system" in bad_identity
    bad_identity["system"][required] = ""
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)

    # Test missing values
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    assert "system" in bad_identity
    bad_identity["system"].pop(required, None)
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)


@pytest.mark.parametrize("required", ("client_id", "username"))
def test_service_account_identity_missing_required(required):
    # Test blank values
    bad_identity = copy.deepcopy(SERVICE_ACCOUNT_IDENTITY)
    assert "service_account" in bad_identity
    bad_identity["service_account"][required] = ""
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)

    # Test missing values
    bad_identity = copy.deepcopy(SERVICE_ACCOUNT_IDENTITY)
    assert "service_account" in bad_identity
    bad_identity["service_account"].pop(required, None)
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)


@pytest.mark.parametrize(
    "test_field,bad_value",
    [("org_id", ""), ("org_id", "X" * 37), ("account_number", "X" * 37)],
)
def test_string_length(test_field, bad_value):
    bad_identity = USER_IDENTITY.copy()
    bad_identity[test_field] = bad_value
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)


@pytest.mark.parametrize("test_field", ("type", "auth_type"))
def test_not_one_of(test_field):
    # Test invalid value
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    bad_identity[test_field] = "bad_value"
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)

    # Test blank value
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    bad_identity[test_field] = ""
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)


def test_bad_cert_type():
    bad_identity = copy.deepcopy(SYSTEM_IDENTITY)
    bad_identity["system"]["cert_type"] = "bad_value"
    with pytest.raises(ValueError):
        identity_test_common(bad_identity)
