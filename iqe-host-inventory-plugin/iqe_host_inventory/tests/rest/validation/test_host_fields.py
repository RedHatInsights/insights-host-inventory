from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import ErrorNotificationWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.datagen_utils import HOST_FIELDS
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import generate_facts
from iqe_host_inventory.utils.datagen_utils import generate_host_field_value
from iqe_host_inventory.utils.datagen_utils import generate_ips
from iqe_host_inventory.utils.datagen_utils import generate_macs
from iqe_host_inventory.utils.datagen_utils import generate_provider_type
from iqe_host_inventory.utils.datagen_utils import generate_random_mac_address
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_host_field_by_name
from iqe_host_inventory.utils.datagen_utils import get_id_facts
from iqe_host_inventory.utils.datagen_utils import parametrize_field

from .test_system_profile import EMPTY_BASICS
from .test_system_profile import INCORRECT_STRING_VALUES

pytestmark = [pytest.mark.backend]


@pytest.fixture
def validate_correct_value(host_inventory: ApplicationHostInventory):
    def _validate(field: Field, value: Any, extra_data: dict[str, Any] | None = None):
        if extra_data is None:
            extra_data = {}
        extra_data[field.name] = value

        host_data = host_inventory.datagen.create_host_data(**extra_data)
        assert host_data[field.name] == value
        host = host_inventory.kafka.create_host(
            host_data, wait_for_created=(field.name != "org_id")
        )
        if value == []:
            assert getattr(host, field.name) is None
        else:
            actual_value = getattr(host, field.name)
            # todo: unify datetime usage
            if isinstance(actual_value, datetime) and not isinstance(value, datetime):
                actual_value = actual_value.isoformat()

            assert actual_value == value
        if field.name == "org_id":
            return  # skipping here due to identity filtering
        rest_host = host_inventory.apis.hosts.get_host_by_id(host)
        assert rest_host.id == host.id

        field_value = getattr(rest_host, field.name)
        if isinstance(field_value, datetime):
            assert field_value.isoformat() == value
        elif field.name == "facts":
            converted_facts = []
            for fact in field_value:
                converted_facts.append(fact.to_dict())
            assert sorted(value) == sorted(converted_facts)
        elif value == []:
            assert field_value is None
        else:
            assert field_value == value

    return _validate


@pytest.fixture
def validate_incorrect_value(host_inventory: ApplicationHostInventory):
    def _validate(field: Field, value: Any, extra_data: dict[str, Any] | None = None):
        if extra_data is None:
            extra_data = {}
        extra_data[field.name] = value

        host_data = host_inventory.datagen.create_host_data(**extra_data)
        if field.name == "org_id" and value is None:
            host_data["org_id"] = None

        to_match = (
            ErrorNotificationWrapper.insights_id
            if field.name != "insights_id"
            else ErrorNotificationWrapper.subscription_manager_id
        )
        host_inventory.kafka.produce_host_create_messages([host_data])
        host_inventory.kafka.wait_for_filtered_error_message(
            to_match,
            host_data["insights_id" if field.name != "insights_id" else "subscription_manager_id"],
        )

        if field.name != "insights_id":
            host_inventory.apis.hosts.verify_not_created(
                retries=1, insights_id=host_data["insights_id"]
            )
        else:
            host_inventory.apis.hosts.verify_not_created(
                retries=1, display_name=host_data["display_name"]
            )

    yield _validate


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "field", [field for field in HOST_FIELDS if not field.is_canonical and field.type != "uuid"]
)
def test_validate_null_fields(validate_incorrect_value, field):
    """
    Test creating host with null value in fields fails

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of null value in host fields
    """
    validate_incorrect_value(field, None)


@pytest.mark.ephemeral
@parametrize_field(HOST_FIELDS, is_required=True)
def test_validate_required_fields(host_inventory: ApplicationHostInventory, field: Field):
    """
    Test creating host without required fields fails

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-required-fields
        negative: true
        title: Validation of required fields
    """
    host_data = host_inventory.datagen.create_host_data()
    del host_data[field.name]

    host_inventory.kafka.produce_host_create_messages([host_data])
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(retries=1, insights_id=host_data["insights_id"])


@pytest.mark.ephemeral
@parametrize_field(get_id_facts())
def test_validate_one_id_is_enough(host_inventory: ApplicationHostInventory, field: Field):
    """
    Test that creating a host with only one ID fact is okay

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create, inv-mq-id-fact-required
        title: Test that creating a host with only one ID fact is okay
    """
    host_data = host_inventory.datagen.create_host_data()
    for host_field in HOST_FIELDS:
        if not host_field.is_required:
            host_data.pop(host_field.name, None)
    host_data[field.name] = generate_host_field_value(field)

    # when provider_type or provider_id is provided, the other one is also required
    if field.name == "provider_id":
        host_data["provider_type"] = generate_provider_type()

    host_inventory.kafka.create_host(host_data, field_to_match=getattr(HostWrapper, field.name))


@pytest.mark.ephemeral
@iqe_blocker(iqe_blocker.jira("RHINENG-16546", category=iqe_blocker.PRODUCT_RFE))
def test_validate_at_least_one_id_fact_required(host_inventory: ApplicationHostInventory):
    """
    Test that creating a host without any ID facts fails

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-id-fact-required
        negative: true
        title: Test that creating a host without any ID facts fails
    """
    host_data = host_inventory.datagen.create_host_data()
    for field in HOST_FIELDS:
        if field.is_id_fact:
            host_data.pop(field.name, None)
    host_data.pop("provider_type", None)

    host_inventory.kafka.produce_host_create_messages([host_data])
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(display_name=host_data["display_name"])


@pytest.mark.ephemeral
@parametrize_field(HOST_FIELDS, type="str")
def test_validate_string_fields_length(validate_correct_value, validate_incorrect_value, field):
    """
    Test minimum and maximum length of string fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of string fields length
    """

    def _test_correct_length(min_length, max_length):
        value = generate_string_of_length(min_length, max_length)
        if field.is_canonical:
            value = value.lower()
        validate_correct_value(field, value, extra_data)

    def _test_wrong_length(length):
        value = generate_string_of_length(length)
        if field.is_canonical:
            value = value.lower()
        validate_incorrect_value(field, value, extra_data)

    name = field.name
    min_len = field.min_len
    max_len = field.max_len

    # provider_type is required together with provider_id
    extra_data = {}
    if name == "provider_id":
        extra_data["provider_type"] = generate_provider_type()

    # Random length within range
    _test_correct_length(min_len, max_len)
    # Minimum length
    _test_correct_length(min_len, min_len)
    # Maximum length
    _test_correct_length(max_len, max_len)
    # Less than minimum length
    if min_len > 0:
        _test_wrong_length(min_len - 1)
    # More than maximum length
    _test_wrong_length(max_len + 1)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", INCORRECT_STRING_VALUES)
@parametrize_field(HOST_FIELDS, type="str")
def test_validate_string_fields_incorrect(validate_incorrect_value, field, value):
    """
    Test incorrect values for string fields

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in string fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@parametrize_field(HOST_FIELDS, lambda x: "uuid" in x.type)
def test_validate_uuid_fields_correct(validate_correct_value, field):
    """
    Test correct values for uuid fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in uuid fields
    """
    validate_correct_value(field, generate_uuid())


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "value",
    [
        *EMPTY_BASICS,
        pytest.param([generate_uuid()], id="list"),
        pytest.param(generate_uuid().replace("-", ""), id="no-dashes"),
        pytest.param(generate_uuid().replace("-", "_"), id="underscores"),
        pytest.param(generate_uuid()[:23], id="short"),
        pytest.param(generate_uuid()[:35], id="short2"),
        pytest.param(generate_uuid() + "a", id="extra char"),
        pytest.param("f8c1684c-aáe7-4463-8cf4-773cc668862c", id="accent"),
        pytest.param("f8c1684c-a$e7-4463-8cf4-773cc668862c", id="special"),
        pytest.param("f8c1684c-aae7-4463-8cf4-773cc6-68862", id="bad dash"),
        pytest.param(generate_uuid()[:10], id="very_short"),
        pytest.param(generate_string_of_length(10, use_letters=False), id="randstr10nolettwe"),
        pytest.param(generate_string_of_length(10, use_punctuation=False), id="randstr10nopunc"),
        pytest.param(
            generate_string_of_length(9, use_letters=False, use_punctuation=False),
            id="randstr(9, no letter no punc)",
        ),
        pytest.param(
            generate_string_of_length(11, use_letters=False, use_punctuation=False),
            id="randstr(11, no letter no punc)",
        ),
    ],
)
@parametrize_field(HOST_FIELDS, lambda x: "uuid" in x.type)
def test_validate_uuid_fields_incorrect(validate_incorrect_value, field, value):
    """
    Test incorrect values for uuid fields

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in uuid fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@parametrize_field(HOST_FIELDS, type="sat_uuid")
def test_validate_uuid_sat_fields_correct(validate_correct_value, field):
    """
    Test correct values for sat_uuid fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in sat_uuid fields
    """
    value = generate_string_of_length(10, use_letters=False, use_punctuation=False)
    validate_correct_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "value",
    [
        pytest.param([], id="n=0"),
        pytest.param(generate_ips(1), id="n=1"),
        pytest.param(generate_ips(2), id="n=2"),
        pytest.param(generate_ips(10), id="n=10"),
    ],
)
@parametrize_field(HOST_FIELDS, type="ip_addr")
def test_validate_ip_address_fields_correct(validate_correct_value, field, value):
    """
    Test correct values for ip_address fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in ip_address fields
    """
    validate_correct_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "value",
    [
        pytest.param({}, id="empty dict"),
        pytest.param("", id="empty_string"),
        pytest.param([None], id="list just none"),
        pytest.param([""], id="list just empty"),
        pytest.param([None, *generate_ips()], id="list with none"),
        pytest.param(["", *generate_ips()], id="list with empty"),
        pytest.param(generate_ips(1)[0], id="just element"),
        pytest.param([generate_ips(1)[0].replace(".", ",")], id="commas"),
        pytest.param([generate_ips(1)[0].replace(".", ":")], id="colons"),
        pytest.param([generate_ips(1)[0].replace(".", " ")], id="spaces"),
        pytest.param([generate_ips(1)[0].replace(".", "")], id="dots"),
        pytest.param([generate_ips(1)[0] + ".192"], id="extra segment"),
        pytest.param(["64.333.161.147"], id="bad range"),
        pytest.param(["64.233.161,147"], id="typo"),
        pytest.param([generate_string_of_length(14)], id="randstr"),
        pytest.param(generate_macs(), id="mac given"),
    ],
)
@parametrize_field(HOST_FIELDS, type="ip_addr")
def test_validate_ip_address_fields_incorrect(validate_incorrect_value, field, value):
    """
    Test incorrect values for uuid fields

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in ip_address fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(generate_macs(1), id="one random"),
        pytest.param(generate_macs(2), id="2 random"),
        pytest.param(generate_macs(10), id="10 random"),
        pytest.param([generate_macs(1)[0].replace(":", "-")], id="dashes"),
        pytest.param([generate_macs(1)[0].replace(":", "")], id="compact"),
        pytest.param(["0123.4567.89ab"], id="dot-form"),
    ],
)
@parametrize_field(HOST_FIELDS, type="mac_addr")
def test_validate_mac_address_fields_correct(validate_correct_value, field, value):
    """
    Test correct values for mac_address fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in mac_address fields
    """
    validate_correct_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "value",
    [
        *EMPTY_BASICS,
        pytest.param([None], id="list just None"),
        pytest.param([""], id="list just empty"),
        pytest.param([None, *generate_macs()], id="list with None"),
        pytest.param(["", *generate_macs()], id="list with empty"),
        pytest.param(generate_macs(1)[0], id="element instead of list"),
        pytest.param([generate_macs(1)[0].replace(":", ",")], id="commas"),
        pytest.param([generate_macs(1)[0].replace(":", ".")], id="dots"),
        pytest.param([generate_macs(1)[0].replace(":", " ")], id="spaces"),
        pytest.param([generate_macs(1)[0] + ":AB"], id="added extra"),
        pytest.param(["00:FG:20:83:53:D1"], id="bad mac"),
        pytest.param([generate_string_of_length(17)], id="randstr"),
        pytest.param([generate_random_mac_address(21)], id="too_long"),
        pytest.param(generate_ips(), id="ips"),
    ],
)
@parametrize_field(HOST_FIELDS, type="mac_addr")
def test_validate_mac_address_fields_incorrect(validate_incorrect_value, field, value):
    """
    Test incorrect values for mac_address fields

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in mac_address fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("other_mac_address", [True, False])
def test_validate_mac_addresses_removes_zero_mac_address(
    host_inventory: ApplicationHostInventory, other_mac_address: bool, request
):
    """
    https://issues.redhat.com/browse/RHINENG-12053

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-remove-zero-mac_address
        title: Test that Inventory removes zero mac address from the payload
    """
    host_data = host_inventory.datagen.create_host_data()
    macs_without_zero = generate_macs(1) if other_mac_address else None
    host_data["mac_addresses"] = (macs_without_zero or []) + ["00:00:00:00:00:00"]

    host = host_inventory.kafka.create_host(host_data=host_data)

    assert host.mac_addresses == macs_without_zero
    response_host = host_inventory.apis.hosts.get_host_by_id(host)
    assert response_host.mac_addresses == macs_without_zero


@pytest.mark.ephemeral
@parametrize_field(HOST_FIELDS, type="enum")
def test_validate_enum_fields_correct(validate_correct_value, field: Field):
    """
    Test correct values for enum fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in enum fields
    """
    # provider_id is required together with provider_type
    extra_data = {}
    if field.name == "provider_type":
        extra_data["provider_id"] = generate_uuid()
    assert field.correct_values is not None
    for value in field.correct_values:
        if field.name == "provider_type":  # TODO: bug - different values should dedup
            extra_data["provider_id"] = generate_uuid()
        print(field.name, value)
        validate_correct_value(field, value, extra_data)


@pytest.mark.ephemeral
@parametrize_field(HOST_FIELDS, type="enum")
def test_validate_enum_fields_incorrect(validate_incorrect_value, field: Field):
    """
    Test incorrect values for enum fields

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in enum fields
    """
    # provider_id is required together with provider_type
    extra_data = {}
    if field.name == "provider_type":
        extra_data["provider_id"] = generate_uuid()

    assert field.correct_values is not None

    correct_value = field.correct_values[0]
    incorrect_values = [
        generate_uuid(),
        "string",
        "!@#$%^&*()",
        "",
        " ",
        [],
        {},
        generate_string_of_length(len(correct_value), use_digits=False, use_punctuation=False),
        correct_value + " ",
        correct_value[: len(correct_value) - 1],
    ]

    for value in incorrect_values:
        validate_incorrect_value(field, value, extra_data)


_PT = get_host_field_by_name("provider_type")
assert _PT.correct_values is not None
_CORRECT_PROVIDER_TYPE_VALUES: list[str] = _PT.correct_values


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", _CORRECT_PROVIDER_TYPE_VALUES)
def test_validate_provider_type_without_provider_id(
    host_inventory: ApplicationHostInventory, value: str
):
    """Test creating host with provider_type without provider_id
    metadata:
        requirements: inv-provider-fields
        importance: medium
        assignee: fstavela
        negative: true
        title: Create host with valid "provider_type" but without "provider_id"
    """
    host_data = host_inventory.datagen.create_host_data(provider_type=value)
    host_data.pop("provider_id", None)

    host_inventory.kafka.produce_host_create_messages([host_data])
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(insights_id=host_data["insights_id"])


@pytest.mark.ephemeral
def test_validate_provider_id_without_provider_type(host_inventory: ApplicationHostInventory):
    """Test creating host with provider_id without provider_type
    metadata:
        requirements: inv-provider-fields
        importance: medium
        assignee: fstavela
        negative: true
        title: Create host with valid "provider_id" but without "provider_type"
    """
    host_data = host_inventory.datagen.create_host_data(provider_id=generate_uuid())
    host_data.pop("provider_type", None)

    host_inventory.kafka.produce_host_create_messages([host_data])
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(insights_id=host_data["insights_id"])


@pytest.mark.ephemeral
@parametrize_field(HOST_FIELDS, lambda x: x.is_canonical)
def test_force_canonical_facts_to_lowercase(
    host_inventory: ApplicationHostInventory, field: Field
):
    """Test inventory transforms canonical facts into lowercase

    https://issues.redhat.com/browse/ESSNTL-831

    metadata:
        requirements: inv-mq-canonical-fact
        importance: high
        assignee: fstavela
        title: Transform canonical facts to lowercase
    """
    value = generate_host_field_value(field)
    if isinstance(value, list):
        value = [item.upper() for item in value]
        expected_value = [item.lower() for item in value]
    else:
        value = value.upper()
        expected_value = value.lower()

    host_data = host_inventory.datagen.create_host_data(**{field.name: value})
    if field.name == "provider_id":
        host_data["provider_type"] = generate_provider_type()
    if field.name == "provider_type":
        host_data["provider_id"] = generate_uuid()

    if field.name == "insights_id":
        host = host_inventory.kafka.create_host(
            host_data,
            field_to_match=HostWrapper.subscription_manager_id,
        )
    else:
        host = host_inventory.kafka.create_host(host_data)
    assert getattr(host, field.name) == expected_value
    response_hosts = host_inventory.apis.hosts.get_hosts()
    assert host.id in {response_host.id for response_host in response_hosts}

    response = host_inventory.apis.hosts.get_hosts_by_id_response(host.id)
    assert response.count == 1
    assert getattr(response.results[0], field.name) == expected_value


@pytest.mark.ephemeral
@pytest.mark.parametrize("invalid_account", [None, -5, "invalid-account"])
def test_create_host_with_invalid_account(
    host_inventory: ApplicationHostInventory, invalid_account: str | int | None
):
    """
    Test Host Creation with an invalid account number.

    Invalid values for account_number are rejected during host creation.

    metadata:
        requirements: inv-mq-host-field-validation
        assignee: fstavela
        importance: medium
        negative: true
        title: Inventory API: Host Creation with Invalid Account Number
    """
    host_data = host_inventory.datagen.create_host_data(account_number=invalid_account)  # type: ignore[arg-type]
    if invalid_account is None:
        host_data["account"] = None
    host_inventory.kafka.produce_host_create_messages([host_data])
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(insights_id=host_data["insights_id"])


@pytest.mark.ephemeral
@pytest.mark.parametrize("invalid_org_id", [None, -5, generate_string_of_length(40)])
def test_create_host_with_invalid_org_id(
    host_inventory: ApplicationHostInventory, invalid_org_id: str | int | None
):
    """
    Test Host Creation with an invalid org id.

    Invalid values for org_id are rejected during host creation.

    metadata:
        requirements: inv-mq-host-field-validation
        assignee: fstavela
        importance: medium
        negative: true
        title: Inventory API: Host Creation with Invalid Account Number
    """
    host_data = host_inventory.datagen.create_host_data(org_id=invalid_org_id)  # type: ignore[arg-type]
    if invalid_org_id is None:
        host_data["org_id"] = None
    host_inventory.kafka.produce_host_create_messages([host_data])
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )
    host_inventory.apis.hosts.verify_not_created(insights_id=host_data["insights_id"])


@pytest.mark.ephemeral
def test_validate_facts(validate_correct_value):
    """
    Test correct values for facts field

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in facts field
    """
    facts_field = get_host_field_by_name("facts")
    validate_correct_value(facts_field, generate_facts())


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "facts",
    [
        [{"namespace": "rhsm", "facts": {"": "invalid"}}],
        [{"namespace": "rhsm", "facts": {"metadata": {"": "invalid"}}}],
        [{"namespace": "rhsm", "facts": {"foo": "bar", "": "invalid"}}],
        [
            {"namespace": "rhsm", "facts": {"foo": "bar"}},
            {"namespace": "foo", "facts": {"": "invalid"}},
        ],
    ],
)
def test_validate_facts_empty_json_keys(facts, validate_incorrect_value):
    """
    Test empty json keys validation for the facts field.

    metadata:
        requirements: inv-mq-host-field-validation
        assignee: fstavela
        importance: medium
        negative: true
        title: Inventory API: Test validation of empty json keys in facts field
    """
    facts_field = get_host_field_by_name("facts")
    validate_incorrect_value(facts_field, facts)
