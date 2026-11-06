from base64 import b64encode
from copy import deepcopy
from json import dumps

import pytest

from app.auth.forwarded_identity import FORWARDED_IDENTITY_HEADER
from app.auth.forwarded_identity import get_satellite_forwarded_identity
from app.auth.identity import SHARED_SECRET_ENV_VAR
from app.auth.identity import Identity
from app.auth.identity import from_auth_header
from app.auth.identity import from_bearer_token
from app.exceptions import InventoryException
from tests.helpers.test_utils import SATELLITE_IDENTITY
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import set_environment

MALFORMED_FORWARDED_IDENTITIES = ("not-a-uuid", "abcdef", "123", "0.0")
FORWARDED_SUBMAN_ID = generate_uuid()
SHARED_SECRET = "ImaSecret"


def _identity():
    """
    Helper function for Identity module constructors.
    """
    return Identity(USER_IDENTITY)


def _build_id(shared_secret):
    identity = from_bearer_token(shared_secret)
    return identity


def test_valid_auth_identity_from_auth_header(subtests):
    """
    Tests creating an Identity from a Base64 encoded JSON string, which is what is in
    the HTTP header.
    Initialize the Identity object with an encoded payload – a base64-encoded JSON.
    That would typically be a raw HTTP header content.
    """
    expected_identity = _identity()

    identity_data = expected_identity._asdict()

    identity_data_dicts = [
        identity_data,
        # Test with extra data in the identity dict
        {**identity_data, **{"extra_data": "value"}},
    ]

    for identity_data in identity_data_dicts:
        with subtests.test(identity_data=identity_data):
            identity = {"identity": identity_data}
            json = dumps(identity)
            base64 = b64encode(json.encode())

            actual_identity = from_auth_header(base64)
            assert expected_identity.__dict__ == actual_identity.__dict__
            assert actual_identity.is_trusted_system is False


def test_invalid_type_auth_identity_from_auth_header():
    """
    Initializing the Identity object with an invalid type that can't be a Base64
    encoded payload should raise a TypeError.
    """
    with pytest.raises(TypeError):
        from_auth_header(["not", "a", "string"])


def test_invalid_value_auth_identity_from_auth_header():
    """
    Initializing the Identity object with an invalid Base6č encoded payload should
    raise a ValueError.
    """
    with pytest.raises(ValueError):
        from_auth_header("invalid Base64")


def test_invalid_format_auth_identity_from_auth_header():
    """
    Initializing the Identity object with an valid Base64 encoded payload
    that does not contain the "identity" field.
    """
    identity = _identity()

    dict_ = identity._asdict()
    json = dumps(dict_)
    base64 = b64encode(json.encode())

    with pytest.raises(KeyError):
        from_auth_header(base64)


def test_get_satellite_forwarded_identity_returns_none_for_non_satellite_identity() -> None:
    identity = Identity(SYSTEM_IDENTITY)
    assert get_satellite_forwarded_identity(identity) is None


def test_get_satellite_forwarded_identity_returns_none_without_header(flask_app) -> None:
    identity = Identity(SATELLITE_IDENTITY)
    with flask_app.app.test_request_context():
        assert get_satellite_forwarded_identity(identity) is None


def test_get_satellite_forwarded_identity_returns_uuid(flask_app) -> None:
    identity = Identity(SATELLITE_IDENTITY)
    with flask_app.app.test_request_context(headers={FORWARDED_IDENTITY_HEADER: FORWARDED_SUBMAN_ID}):
        assert get_satellite_forwarded_identity(identity) == FORWARDED_SUBMAN_ID


@pytest.mark.parametrize("invalid_uuid", MALFORMED_FORWARDED_IDENTITIES)
def test_get_satellite_forwarded_identity_rejects_malformed_header(flask_app, invalid_uuid: str) -> None:
    identity = Identity(SATELLITE_IDENTITY)
    with flask_app.app.test_request_context(headers={FORWARDED_IDENTITY_HEADER: invalid_uuid}):
        with pytest.raises(InventoryException) as exc_info:
            get_satellite_forwarded_identity(identity)
        assert exc_info.value.status == 403


def test_valid_auth_identity_validate():
    Identity(USER_IDENTITY)


def test_invalid_org_id_auth_identity_validate(subtests):
    test_identity = deepcopy(USER_IDENTITY)
    org_ids = [None, ""]
    for org_id in org_ids:
        with subtests.test(org_id=org_id):
            test_identity["org_id"] = org_id
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_invalid_type_auth_identity_validate(subtests):
    test_identity = deepcopy(USER_IDENTITY)
    identity_types = [None, ""]
    for identity_type in identity_types:
        with subtests.test(identity_type=identity_type):
            test_identity["type"] = identity_type
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_invalid_system_obj_auth_identity_validate(subtests):
    test_identity = deepcopy(SYSTEM_IDENTITY)
    system_objects = [None, ""]
    for system_object in system_objects:
        with subtests.test(system_object=system_object):
            test_identity["system"] = system_object
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_invalid_service_account_obj_auth_identity_validate(subtests):
    test_identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    service_account_objects = [
        None,
        "",
        {
            "client_id": SERVICE_ACCOUNT_IDENTITY["service_account"]["client_id"],
            "username": "",
        },
        {"client_id": "", "username": SERVICE_ACCOUNT_IDENTITY["service_account"]["username"]},
    ]
    for service_account_object in service_account_objects:
        with subtests.test(service_account_object=service_account_object):
            test_identity["service_account"] = service_account_object
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_service_account_optional_fields_auth_identity_validate():
    # Test that service_account identity validates without optional fields (user_id, scope)
    test_identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    test_identity["service_account"] = {
        "client_id": SERVICE_ACCOUNT_IDENTITY["service_account"]["client_id"],
        "username": SERVICE_ACCOUNT_IDENTITY["service_account"]["username"],
    }
    # Should not raise - user_id and scope are optional
    Identity(test_identity)


def test_invalid_auth_types_auth_identity_validate(subtests):
    test_identities = [deepcopy(USER_IDENTITY), deepcopy(SYSTEM_IDENTITY), deepcopy(SERVICE_ACCOUNT_IDENTITY)]
    auth_types = ["", "foo"]
    for test_identity in test_identities:
        for auth_type in auth_types:
            with subtests.test(auth_type=auth_type):
                test_identity["auth_type"] = auth_type
                with pytest.raises(ValueError):
                    Identity(test_identity)


def test_invalid_cert_types_auth_identity_validate(subtests):
    test_identity = deepcopy(SYSTEM_IDENTITY)
    cert_types = [None, "", "foo"]
    for cert_type in cert_types:
        with subtests.test(cert_type=cert_type):
            test_identity["system"]["cert_type"] = cert_type
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_case_insensitive_cert_types_auth_identity_validate(subtests):
    # Validate that cert_type is case-insensitive
    test_identity = deepcopy(SYSTEM_IDENTITY)
    cert_types = ["RHUI", "Satellite", "system"]
    for cert_type in cert_types:
        with subtests.test(cert_type=cert_type):
            test_identity["system"]["cert_type"] = cert_type
            Identity(test_identity)


def test_case_insensitive_auth_types_auth_identity_validate(subtests):
    # Validate that auth_type is case-insensitive
    test_identity = deepcopy(SYSTEM_IDENTITY)
    auth_types = ["JWT-AUTH", "Cert-Auth", "basic-auth"]
    for auth_type in auth_types:
        with subtests.test(auth_type=auth_type):
            test_identity["auth_type"] = auth_type
            Identity(test_identity)


def test_obsolete_auth_type_auth_identity_validate():
    # Validate that removed auth_type not working anymore
    test_identity = deepcopy(SYSTEM_IDENTITY)
    test_identity["auth_type"] = "CLASSIC-PROXY"
    with pytest.raises(ValueError):
        Identity(test_identity)


def test_missing_auth_type_auth_identity_validate():
    # auth_type must be provided
    test_identity = deepcopy(SYSTEM_IDENTITY)
    test_identity["auth_type"] = None
    with pytest.raises(ValueError):
        Identity(test_identity)


def test_validation_trusted_identity():
    with set_environment({SHARED_SECRET_ENV_VAR: SHARED_SECRET}):
        _build_id(SHARED_SECRET)


def test_validation_with_invalid_identity_trusted_identity():
    with pytest.raises(ValueError):
        from_bearer_token("InvalidPassword")


def test_validation_env_var_not_set_trusted_identity():
    with set_environment({}):
        with pytest.raises(ValueError):
            _build_id(SHARED_SECRET)


def test_validation_token_is_None_trusted_identity(subtests):
    tokens = [None, ""]
    for token in tokens:
        with subtests.test(token_value=token):
            with pytest.raises(ValueError):
                Identity(token=token)


def test_is_trusted_system_trusted_identity():
    with set_environment({SHARED_SECRET_ENV_VAR: SHARED_SECRET}):
        identity = _build_id(SHARED_SECRET)

    assert identity.is_trusted_system is True


def test_org_id_is_not_set_for_trusted_system_trusted_identity():
    with set_environment({SHARED_SECRET_ENV_VAR: SHARED_SECRET}):
        identity = _build_id(SHARED_SECRET)

    assert not hasattr(identity, "org_id")
