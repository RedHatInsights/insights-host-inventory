import json
import logging
import warnings
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from random import randint
from secrets import token_hex

import pytest
from dateutil.parser import parse as parse_datetime

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import ErrorNotificationWrapper
from iqe_host_inventory.utils.datagen_utils import SYSTEM_PROFILE
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import generate_digits
from iqe_host_inventory.utils.datagen_utils import generate_ips
from iqe_host_inventory.utils.datagen_utils import generate_ipv6s
from iqe_host_inventory.utils.datagen_utils import generate_macs
from iqe_host_inventory.utils.datagen_utils import generate_random_mac_address
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_timestamp
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name
from iqe_host_inventory.utils.datagen_utils import parametrize_field

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]

ParameterSet = type(pytest.param())


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "non_ascii_unicode_character,charset",
    [
        ("💩", "utf-8"),
        ("☺", "iso-8859-1"),
        ("á", "utf-8"),
        ("ç", "iso-8859-1"),
        ("©", "utf-8"),
        ("€", "iso-8859-1"),
    ],
)
def test_validate_system_profile_yum_repos_allows_non_ascii_unicode_characters(
    host_inventory: ApplicationHostInventory,
    non_ascii_unicode_character: str,
    charset: str,
):
    """
    Test non ascii unicode characters for the yum_repos in system profile.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5059

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation
        title: Inventory: Ensure create a host with non ascii unicode characters in system profile
            is allowed via MQ
    """
    host_data = host_inventory.datagen.create_host_data()

    # This is necessary to simulate the data conversion made by ingress
    non_ascii_unicode_str = json.dumps(non_ascii_unicode_character.encode("utf-8").decode(charset))
    host_data["system_profile"]["yum_repos"] = [{"name": "insights-test-" + non_ascii_unicode_str}]

    logger.info(
        f"Creating a new host by sending a non ascii unicode character: {non_ascii_unicode_str}"
    )
    consumed_host_messages = host_inventory.kafka.create_host_events([host_data])
    assert len(consumed_host_messages) == 1

    consumed_host_message = consumed_host_messages[0]
    assert consumed_host_message.value.get("type") == "created"

    host = consumed_host_message.host

    logger.info("Retrieving host system profile")
    host_inventory.apis.hosts.wait_for_created(host)
    system_profile_response = host_inventory.apis.hosts.get_hosts_system_profile_response(host.id)

    assert system_profile_response.count == 1
    repo_name = system_profile_response.results[0].system_profile.yum_repos[0].name
    assert non_ascii_unicode_str in repo_name


EMPTY_LIST = pytest.param([], id="empty list")
EMPTY_DICT = pytest.param({}, id="empty dict")
LIST_WITH_STR = pytest.param(["a"], id="list with data")
EMPTY_STR = pytest.param("", id="empty str")

EMPTY_BASICS = (EMPTY_LIST, EMPTY_DICT, EMPTY_STR)
SAP_SIDS_EMPTY_BASICS: tuple[object, ...] = (EMPTY_DICT, EMPTY_STR, [[]], [{}], [""], [None])
INCORRECT_STRING_VALUES = (EMPTY_LIST, EMPTY_DICT, LIST_WITH_STR)

RANDSTR_5 = (
    pytest.param(generate_string_of_length(5), id="randstr(5)"),
    pytest.param(
        generate_string_of_length(5, use_punctuation=False), id="randstr(5, no_punctuation)"
    ),
    pytest.param(
        generate_string_of_length(5, use_punctuation=False, use_digits=False),
        id="randstr(5, no_punctuation, no_digits)",
    ),
)

INCORRECT_CANONICAL_UUIDS = (
    *EMPTY_BASICS,
    pytest.param([generate_uuid()], id="list of uuid"),
    pytest.param(generate_uuid().replace("-", "_"), id="bad uuid underscore"),
    pytest.param(generate_uuid().replace("-", "."), id="bad uuid dots"),
    pytest.param(generate_uuid().replace("-", " "), id="bad uuid spaces"),
    pytest.param(generate_uuid().replace("-", ""), id="bad uuid no-separator"),
    pytest.param(generate_uuid().upper(), id="uuid uppercase"),
    pytest.param(generate_uuid()[:23], id="uuid short 23"),
    pytest.param(generate_uuid()[:35], id="uuid shoirt 35"),
    pytest.param(generate_uuid() + "a", id="uuid with bad char"),
    pytest.param("f8c1684c-aáe7-4463-8cf4-773cc668862c", id="uuid bad accent"),
    pytest.param("f8c1684c-a$e7-4463-8cf4-773cc668862c", id="uuid special char"),
    pytest.param("f8c1684c-aae7-4463-8cf4-773cc6-68862", id="uuid evil extra dash"),
    pytest.param(generate_uuid()[:10], id="uuid short 10"),
)

CORRECT_INTEGER_VALUES = (
    "0",
    "-0",
    pytest.param("0000" + generate_digits(5), id="leading zeroes"),
    pytest.param(generate_digits(1), id="random digit"),
)

INCORRECT_INTEGER_VALUES = (
    *EMPTY_BASICS,
    pytest.param(["123"], id="list of int"),
    pytest.param("12.5", id="float"),
    *RANDSTR_5,
)

CORRECT_BOOLEAN_VALUES = ("true", "false", "TRUE", "FALSE", "True", "False")

INCORRECT_BOOLEAN_VALUES: tuple[object, ...] = (
    *EMPTY_BASICS,
    pytest.param(["true"], id="list with true"),
    *RANDSTR_5,
    "ttrue",
)

CORRECT_SAP_SIDS = (
    pytest.param([]),
    pytest.param(["ABC"]),
    pytest.param(["AB0"]),
    pytest.param(["A1C"]),
    pytest.param(["A10"]),
    pytest.param(["ABC", "AB0", "A1C", "A10"], id="list of sids"),
)

INCORRECT_SAP_SIDS = (
    *SAP_SIDS_EMPTY_BASICS,
    pytest.param(["1AB"], id="starts with digit"),
    pytest.param(["ABC", "ABC"], id="not unique"),
    pytest.param(["ABC", "ABC", "ABD"]),
    pytest.param(["abc"], id="lowercase"),
    pytest.param(["aBC"], id="starts with lowercase"),
    pytest.param(["A"], id="one letter"),
    pytest.param(["AB"], id="two letters"),
    pytest.param(["ABCD"], id="four letters"),
    pytest.param(["?BC"], id="special char"),
    pytest.param([["ABC"]], id="list"),
    pytest.param(["abc", "aBC", "A", "AB", "ABCD", "?BC"], id="list of incorrect sids"),
)

CORRECT_SAP_INSTANCE_NUMBER = (
    pytest.param("00"),
    pytest.param("99"),
    pytest.param(generate_digits(2), id="random_digits"),
)

INCORRECT_SAP_INSTANCE_NUMBER = (
    *EMPTY_BASICS,
    pytest.param(None, id="none_value"),
    pytest.param(["55"], id="list with digits"),
    pytest.param("0"),
    pytest.param("9"),
    pytest.param("123"),
    pytest.param("ab"),
    pytest.param(generate_string_of_length(2, use_digits=False), id="randstr(2, no_digits"),
)

CORRECT_SAP_VERSION = (
    "0.00.000.00.0000000000",
    "9.99.999.99.9999999999",
    "1.00.122.04.1478575636",
    pytest.param(
        ".".join([
            generate_digits(1),
            generate_digits(2),
            generate_digits(3),
            generate_digits(2),
            generate_digits(10),
        ]),
        id="randomized_id",
    ),
)

INCORRECT_SAP_VERSION = (
    *EMPTY_BASICS,
    ["1.00.122.04.1478575636"],
    "1.00.122.04.147857563",
    "1.00.122.04.14785756367",
    "00.122.04.1478575636",
    "1.00.122.04",
    "100122041478575636",
    "1001220414785756367890",
    "1.00.1a2.04.1478575636",
    "1.00.1?2.04.1478575636",
)


def _unpack_param(item):
    if isinstance(item, ParameterSet):
        return item.values[0]
    elif isinstance(item, (list, tuple)):
        return [_unpack_param(element) for element in item]
    elif isinstance(item, dict):
        return {key: _unpack_param(val) for key, val in item.items()}
    else:
        return item


def generate_incorrect_enum_values(correct_value):
    return [
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


CORRECT_DATETIMES = (
    pytest.param(generate_timestamp(datetime.now(UTC) - timedelta(days=7)), id="7 days ago"),
    pytest.param(generate_timestamp(datetime.now()), id="now"),
    pytest.param(generate_timestamp(), id="random time"),
    "2021-09-02T16:45:08.951Z",
    "2021-09-02T16:45:08.951",
    "2021-05-11T19:46:56Z",
    "2021-05-11T19:46:56",
    "2018-07-24T16:23:34+00:00",
    "2018-07-24T16:23:34.123+00:00",
    "2021-08-30T03:42:02.284573+00:00",
    "2021-08-30T03:42:02.284573Z",
    "2021-08-30T03:42:02.284573",
)

INCORRECT_DATETIMES = (
    *EMPTY_BASICS,
    pytest.param([generate_timestamp()], id="list of timestamp"),
    pytest.param(generate_uuid(), id="uuid"),
    pytest.param(generate_string_of_length(10), id="randstr(10)"),
)

INCORRECT_MAC_ADDRESSES = (
    *EMPTY_BASICS,
    pytest.param(generate_macs(1), id="list of mac address"),
    pytest.param(generate_macs(1)[0].replace(":", ","), id="mac with comma"),
    pytest.param(generate_macs(1)[0].replace(":", "."), id=" mac with dot"),
    pytest.param(generate_macs(1)[0].replace(":", " "), id="mac with spaces"),
    pytest.param(generate_macs(1)[0] + ":AB", id="mac with extra"),
    pytest.param("00:FG:20:83:53:D1", id="mac with G"),
    pytest.param(generate_string_of_length(17), id="randstr(17)"),
    pytest.param(generate_random_mac_address(21), id="randmac(21)"),
    pytest.param(generate_ips()[0], id="random ip"),
)


@pytest.fixture
def validate_correct_value(  # NOQA: C901
    host_inventory: ApplicationHostInventory,
):
    def _validate(field: Field, value, expected_value=None):
        value = _unpack_param(value)
        host_data = host_inventory.datagen.create_host_data()
        host_data["system_profile"][field.name] = value
        host = host_inventory.kafka.create_host(host_data)

        if isinstance(host.system_profile[field.name], bool):
            assert str(host.system_profile[field.name]).lower() == value.lower()
        elif isinstance(host.system_profile[field.name], int):
            assert host.system_profile[field.name] == int(value)
        else:
            assert host.system_profile[field.name] == value

        response_host = host_inventory.apis.hosts.get_host_system_profile(host)

        response_value = getattr(response_host.system_profile, field.name)
        if hasattr(response_value, "to_dict"):
            response_value = response_value.to_dict()
        if (
            isinstance(response_value, list)
            and len(response_value)
            and hasattr(response_value[0], "to_dict")
        ):
            response_value = [x.to_dict() for x in response_value]
        if expected_value is not None:
            if isinstance(response_value, str):
                expected_value = str(expected_value)
            assert response_value == expected_value
        elif isinstance(response_value, datetime):
            assert parse_datetime(value) == response_value

        elif isinstance(response_value, bool):
            assert str(response_value).lower() == value.lower()
        elif isinstance(response_value, int):
            assert response_value == int(value)
        else:
            assert response_value == value

    yield _validate


@pytest.fixture
def validate_incorrect_value(host_inventory: ApplicationHostInventory):
    def _validate(field, value: object):
        value = _unpack_param(value)
        host_data = host_inventory.datagen.create_host_data()
        host_data["system_profile"][field.name] = value
        host_inventory.kafka.produce_host_create_messages([host_data])
        host_inventory.kafka.wait_for_filtered_error_message(
            ErrorNotificationWrapper.display_name, host_data["display_name"]
        )
        host_inventory.apis.hosts.verify_not_created(
            retries=1, insights_id=host_data["insights_id"]
        )

    yield _validate


def normalize_object(attrs, value):
    expected_value = deepcopy(value)
    for name in attrs:
        if value.get(name) is None:
            expected_value[name] = None
        else:
            expected_value[name] = _unpack_param(value[name])

    return expected_value


@pytest.fixture
def validate_correct_object_array(validate_correct_value):
    def _validate(attrs, field, values):
        expected_values = [normalize_object(attrs, value) for value in values]
        validate_correct_value(field, values, expected_values)

    yield _validate


@pytest.fixture
def validate_correct_disk_devices(validate_correct_object_array):
    field = get_sp_field_by_name("disk_devices")

    def _validate(values):
        disk_devices_attrs = ["device", "label", "mount_point", "options", "type"]
        validate_correct_object_array(disk_devices_attrs, field, values)

    yield _validate


@pytest.fixture
def validate_correct_rhel_ai(validate_correct_value):
    field = get_sp_field_by_name("rhel_ai")

    def _validate(values):
        rhel_ai_attrs = [
            "variant",
            "intel_gaudi_hpu_models",
            "rhel_ai_version_id",
            "nvidia_gpu_models",
            "amd_gpu_models",
        ]
        expected_values = normalize_object(rhel_ai_attrs, values)
        validate_correct_value(field, values, expected_values)

    yield _validate


@pytest.fixture
def validate_correct_yum_repos(validate_correct_object_array):
    def _validate(values):
        yum_repos_attrs = ["id", "name", "gpgcheck", "enabled", "base_url", "mirrorlist"]
        validate_correct_object_array(yum_repos_attrs, get_sp_field_by_name("yum_repos"), values)

    yield _validate


@pytest.fixture
def validate_correct_dnf_modules(validate_correct_object_array):
    def _validate(values):
        dnf_modules_attrs = ["name", "stream"]
        validate_correct_object_array(
            dnf_modules_attrs, get_sp_field_by_name("dnf_modules"), values
        )

    yield _validate


@pytest.fixture
def validate_correct_installed_products(validate_correct_object_array):
    def _validate(values):
        installed_products_attrs = ["name", "id", "status"]
        validate_correct_object_array(
            installed_products_attrs, get_sp_field_by_name("installed_products"), values
        )

    yield _validate


@pytest.fixture
def validate_correct_rhsm(validate_correct_value):
    def _validate(value):
        rhsm_attrs = ["version", "environment_ids"]
        expected_value = normalize_object(rhsm_attrs, value)
        validate_correct_value(get_sp_field_by_name("rhsm"), value, expected_value)

    yield _validate


@pytest.fixture
def validate_correct_network_interfaces(validate_correct_object_array):
    def _validate(values):
        network_interfaces_attrs = [
            "ipv4_addresses",
            "ipv6_addresses",
            "mtu",
            "mac_address",
            "name",
            "state",
            "type",
        ]
        validate_correct_object_array(
            network_interfaces_attrs, get_sp_field_by_name("network_interfaces"), values
        )

    yield _validate


@pytest.fixture
def validate_correct_system_purpose(validate_correct_value):
    field = get_sp_field_by_name("system_purpose")

    def _validate(value):
        system_purpose_attrs = ["usage", "role", "sla"]
        expected_value = normalize_object(system_purpose_attrs, value)
        validate_correct_value(field, value, expected_value)

    yield _validate


@pytest.fixture
def validate_correct_workloads(validate_correct_value):
    field = get_sp_field_by_name("workloads")

    def _validate(value):
        workloads_attrs = [
            "sap",
            "ansible",
            "mssql",
            "crowdstrike",
            "ibm_db2",
            "oracle_db",
            "intersystems",
            "rhel_ai",
        ]
        expected_value = normalize_object(workloads_attrs, value)

        # Define nested attributes for each workload type
        nested_attrs = {
            "ansible": [
                "controller_version",
                "hub_version",
                "catalog_worker_version",
                "sso_version",
            ],
            "crowdstrike": ["falcon_aid", "falcon_backend", "falcon_version"],
            "ibm_db2": ["is_running"],
            "intersystems": ["is_intersystems", "running_instances"],
            "mssql": ["version"],
            "oracle_db": ["is_running"],
            "rhel_ai": [
                "variant",
                "rhel_ai_version_id",
                "gpu_models",
                "ai_models",
                "free_disk_storage",
            ],
            "sap": ["sap_system", "sids", "instance_number", "version"],
        }

        # Ensure nested fields have None when not provided
        if expected_value is not None:  # workloads is not None
            for workload_name, nested_value in expected_value.items():
                if workload_name in nested_attrs:
                    for nested_key in nested_attrs[workload_name]:
                        if nested_value is not None and nested_key not in nested_value:
                            nested_value[nested_key] = None

        validate_correct_value(field, value, expected_value)

    yield _validate


@pytest.fixture
def validate_correct_bootc_status(validate_correct_value):
    field = get_sp_field_by_name("bootc_status")

    def _validate(value):
        bootc_status_attrs = ["booted", "rollback", "staged"]
        expected_value = normalize_object(bootc_status_attrs, value)

        nested_attrs = ["image", "image_digest", "cached_image", "cached_image_digest"]
        if expected_value is not None:  # bootc_status is not None
            for nested_value in expected_value.values():
                for nested_key in nested_attrs:
                    if nested_value is not None and nested_key not in nested_value:
                        # e.g. bootc_status.booted.image doesn't exist
                        nested_value[nested_key] = None

        validate_correct_value(field, value, expected_value)

    yield _validate


@pytest.fixture
def validate_correct_conversions(validate_correct_value):
    field = get_sp_field_by_name("conversions")

    def _validate(value):
        conversions_attrs = ["activity"]
        expected_value = normalize_object(conversions_attrs, value)
        validate_correct_value(field, value, expected_value)

    yield _validate


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE)
def test_validate_system_profile_null_fields(validate_incorrect_value, field):
    """
    Test creating host with null value in system_profile fields fails

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of null value in host system_profile fields
    """
    validate_incorrect_value(field, None)


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE, type="str")
def test_validate_system_profile_string_fields_length(
    validate_correct_value, validate_incorrect_value, field: Field
):
    """
    Test minimum and maximum length of system_profile string fields

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile string fields length
    """

    def _test_correct_length(min_length, max_length):
        value = generate_string_of_length(min_length, max_length)
        validate_correct_value(field, value)

    def _test_wrong_length(length):
        value = generate_string_of_length(length)
        validate_incorrect_value(field, value)

    assert field.min_len is not None
    assert field.max_len is not None
    min_len: int = field.min_len
    max_len: int = field.max_len

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
@parametrize_field(SYSTEM_PROFILE, type="str")
def test_validate_system_profile_string_fields_incorrect(
    validate_incorrect_value, field: Field, value
):
    """
    Test incorrect values for system_profile string fields

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile string fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE, type="canonical_uuid")
def test_validate_system_profile_canonical_uuid_fields_correct(validate_correct_value, field):
    """
    Test correct values for system_profile canonical uuid fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile canonical uuid fields
    """
    validate_correct_value(field, generate_uuid())


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", INCORRECT_CANONICAL_UUIDS)
@parametrize_field(SYSTEM_PROFILE, type="canonical_uuid")
def test_validate_system_profile_canonical_uuid_fields_incorrect(
    validate_incorrect_value, field, value
):
    """
    Test incorrect values for system_profile canonical uuid fields

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile canonical uuid fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE, lambda field: "int" in field.type)
def test_validate_system_profile_integer_fields_min_max(
    validate_correct_value, validate_incorrect_value, field: Field
):
    """
    Test min and max values for system_profile integer fields

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of min and max values in system_profile integer fields
    """
    assert isinstance(field.min, int)
    assert isinstance(field.max, int)
    # Random value within range

    validate_correct_value(field, randint(field.min, field.max))
    # Minimum value
    validate_correct_value(field, field.min)
    # Maximum value
    validate_correct_value(field, field.max)
    # Less than minimum value
    validate_incorrect_value(field, field.min - 1)
    # More than maximum value
    validate_incorrect_value(field, field.max + 1)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", CORRECT_INTEGER_VALUES)
@parametrize_field(SYSTEM_PROFILE, lambda field: "int" in field.type)
def test_validate_system_profile_integer_fields_correct(validate_correct_value, field, value):
    """
    Test correct values for system_profile integer fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile integer fields
    """
    validate_correct_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", INCORRECT_INTEGER_VALUES)
@parametrize_field(SYSTEM_PROFILE, lambda field: "int" in field.type)
def test_validate_system_profile_integer_fields_incorrect(validate_incorrect_value, field, value):
    """
    Test incorrect values for system_profile integer fields

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile integer fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", CORRECT_BOOLEAN_VALUES)
@parametrize_field(SYSTEM_PROFILE, type="bool")
def test_validate_system_profile_boolean_fields_correct(validate_correct_value, field, value):
    """
    Test correct values for system_profile boolean fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile boolean fields
    """
    validate_correct_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", INCORRECT_BOOLEAN_VALUES)
@parametrize_field(SYSTEM_PROFILE, type="bool")
def test_validate_system_profile_boolean_fields_incorrect(validate_incorrect_value, field, value):
    """
    Test incorrect values for system_profile boolean fields

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile boolean fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE, type="enum")
def test_validate_system_profile_enum_fields_correct(validate_correct_value, field):
    """
    Test correct values for system_profile enum fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile enum fields
    """
    for value in field.correct_values:
        validate_correct_value(field, value)


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE, type="enum")
def test_validate_system_profile_enum_fields_incorrect(validate_incorrect_value, field):
    """
    Test incorrect values for system_profile enum fields

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile enum fields
    """
    for value in generate_incorrect_enum_values(field.correct_values[0]):
        validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", CORRECT_DATETIMES)
@parametrize_field(SYSTEM_PROFILE, type="date-time")
def test_validate_system_profile_date_time_fields_correct(validate_correct_value, field, value):
    """
    Test correct values for system_profile date-time fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile date-time fields
    """
    validate_correct_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", INCORRECT_DATETIMES)
@parametrize_field(SYSTEM_PROFILE, type="date-time")
def test_validate_system_profile_date_time_fields_incorrect(
    validate_incorrect_value, field, value
):
    """
    Test incorrect values for system_profile date-time fields

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile date-time fields
    """
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE, type="array")
def test_validate_system_profile_array_fields_correct(  # NOQA: C901
    validate_correct_value, field: Field
):
    """
    Test correct values for system_profile array fields

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile array fields
    """
    validate_correct_value(field, [])
    assert field.item_type is not None
    if field.item_type == "str":
        min_len = field.min_len
        max_len = field.max_len
        assert min_len is not None

        assert max_len is not None
        validate_correct_value(field, [generate_string_of_length(min_len, max_len)])
        validate_correct_value(field, [generate_string_of_length(min_len, min_len)])
        validate_correct_value(field, [generate_string_of_length(max_len, max_len)])
        validate_correct_value(
            field, [generate_string_of_length(min_len, max_len) for _ in range(100)]
        )
    if field.item_type == "canonical_uuid":
        validate_correct_value(field, [generate_uuid()])
        validate_correct_value(field, [generate_uuid() for _ in range(100)])
    if "int" in field.item_type:
        for value in CORRECT_INTEGER_VALUES:
            validate_correct_value(field, [value])
        validate_correct_value(field, CORRECT_INTEGER_VALUES)
    if field.item_type == "bool":
        for value in CORRECT_BOOLEAN_VALUES:
            validate_correct_value(field, [value])
        validate_correct_value(field, CORRECT_BOOLEAN_VALUES)
    if field.item_type == "enum":
        assert field.correct_values is not None
        for value in field.correct_values:
            validate_correct_value(field, [value])
        validate_correct_value(field, field.correct_values)
    if field.item_type == "date-time":
        for value in CORRECT_DATETIMES:
            validate_correct_value(field, [value])
        validate_correct_value(field, CORRECT_DATETIMES)


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE, type="array")
def test_validate_system_profile_array_fields_incorrect(  # NOQA: C901
    validate_incorrect_value, field: Field
):
    """
    Test incorrect values for system_profile array fields

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile array fields
    """
    validate_incorrect_value(field, [None])

    assert field.item_type is not None
    if field.item_type == "str":
        min_len = field.min_len
        max_len = field.max_len

        assert min_len is not None
        assert max_len is not None
        if min_len > 0:
            validate_incorrect_value(field, [generate_string_of_length(min_len - 1)])
        validate_incorrect_value(field, [generate_string_of_length(max_len + 1)])
        validate_incorrect_value(
            field,
            [generate_string_of_length(min_len, max_len) for _ in range(99)]
            + [_unpack_param(INCORRECT_STRING_VALUES[0])],
        )
        for value in INCORRECT_STRING_VALUES:
            validate_incorrect_value(field, [value])
    if field.item_type == "canonical_uuid":
        validate_incorrect_value(
            field,
            [generate_uuid() for _ in range(99)] + [_unpack_param(INCORRECT_CANONICAL_UUIDS[0])],
        )
        for value in INCORRECT_CANONICAL_UUIDS:
            validate_incorrect_value(field, [value])
    if "int" in field.item_type:
        validate_incorrect_value(
            field,
            [generate_digits(5) for _ in range(99)] + [_unpack_param(INCORRECT_INTEGER_VALUES[0])],
        )
        for value in INCORRECT_INTEGER_VALUES:
            validate_incorrect_value(field, [value])
    if field.item_type == "bool":
        validate_incorrect_value(field, [*CORRECT_BOOLEAN_VALUES, INCORRECT_BOOLEAN_VALUES[0]])
        for value_b in INCORRECT_BOOLEAN_VALUES:
            validate_incorrect_value(field, [value_b])
    if field.item_type == "enum":
        assert field.correct_values is not None
        validate_incorrect_value(
            field,
            field.correct_values + [generate_incorrect_enum_values(field.correct_values[0])][0],
        )
        for value in generate_incorrect_enum_values(field.correct_values[0]):
            validate_incorrect_value(field, [value])
    if field.item_type == "date-time":
        validate_incorrect_value(field, CORRECT_DATETIMES + INCORRECT_DATETIMES[:1])
        for value in INCORRECT_DATETIMES:
            validate_incorrect_value(field, [value])


@pytest.mark.ephemeral
def test_validate_system_profile_disk_devices(
    validate_correct_disk_devices, validate_incorrect_value
):
    """
    Test validation of system_profile disk_devices field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile disk_devices field
    """
    # device
    field = get_sp_field_by_name("disk_devices")
    validate_correct_disk_devices([{"device": generate_string_of_length(0)}])
    validate_correct_disk_devices([{"device": generate_string_of_length(2048)}])
    validate_incorrect_value(field, [{"device": generate_string_of_length(2049)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(field, [{"device": value}])

    # label
    validate_correct_disk_devices([{"label": generate_string_of_length(0)}])
    validate_correct_disk_devices([{"label": generate_string_of_length(1024)}])
    validate_incorrect_value(field, [{"label": generate_string_of_length(1025)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(field, [{"label": value}])

    # mount_point
    validate_correct_disk_devices([{"mount_point": generate_string_of_length(0)}])
    validate_correct_disk_devices([{"mount_point": generate_string_of_length(2048)}])
    validate_incorrect_value(field, [{"mount_point": generate_string_of_length(2049)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(field, [{"mount_point": value}])

    # type
    validate_correct_disk_devices([{"type": generate_string_of_length(0)}])
    validate_correct_disk_devices([{"type": generate_string_of_length(256)}])
    validate_incorrect_value(field, [{"type": generate_string_of_length(257)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(field, [{"type": value}])

    # options
    validate_correct_disk_devices([{"options": {}}])
    validate_correct_disk_devices([{"options": {generate_string_of_length(1, 100): ""}}])
    validate_correct_disk_devices(
        [{"options": {generate_string_of_length(1, 100): generate_string_of_length(1, 100)}}],
    )
    validate_correct_disk_devices(
        [
            {
                "options": {
                    generate_string_of_length(1, 100): {
                        generate_string_of_length(1, 100): generate_string_of_length(1, 100)
                    }
                }
            }
        ],
    )
    validate_incorrect_value(field, [{"options": {"": generate_string_of_length(1, 100)}}])
    validate_incorrect_value(field, [{"options": generate_string_of_length(1, 100)}])
    validate_incorrect_value(field, [{"options": []}])

    correct_disk_device = {
        "device": "/dev/fdd0",
        "label": "test",
        "mount_point": "/mnt/remote_nfs_shares",
        "type": "ext3",
        "options": {"uid": "0", "ro": "true"},
    }
    incorrect_disk_device = deepcopy(correct_disk_device)
    incorrect_disk_device["device"] = generate_string_of_length(2049)
    validate_correct_disk_devices([])
    validate_correct_disk_devices([{}])
    validate_correct_disk_devices([correct_disk_device])
    validate_correct_disk_devices([correct_disk_device for _ in range(10)])
    validate_incorrect_value(field, [incorrect_disk_device])
    validate_incorrect_value(
        field, [correct_disk_device for _ in range(10)] + [incorrect_disk_device]
    )


mirrorlist = (
    "https://rhui.redhat.com/pulp/mirror/content/dist/rhel8/rhui/$releasever/$basearch/baseos/os"
)


@pytest.mark.ephemeral
def test_validate_system_profile_yum_repos(validate_correct_yum_repos, validate_incorrect_value):
    """
    Test validation of system_profile yum_repos field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile yum_repos field
    """
    yum_repos = get_sp_field_by_name("yum_repos")
    # id
    validate_correct_yum_repos([{"id": generate_string_of_length(0)}])
    validate_correct_yum_repos([{"id": generate_string_of_length(256)}])
    validate_incorrect_value(yum_repos, [{"id": generate_string_of_length(257)}])
    for value_s in INCORRECT_STRING_VALUES:
        validate_incorrect_value(yum_repos, [{"id": value_s}])

    # name
    validate_correct_yum_repos([{"name": generate_string_of_length(0)}])
    validate_correct_yum_repos([{"name": generate_string_of_length(1024)}])
    validate_incorrect_value(yum_repos, [{"name": generate_string_of_length(1025)}])
    for value_s in INCORRECT_STRING_VALUES:
        validate_incorrect_value(yum_repos, [{"name": value_s}])

    # base_url
    validate_correct_yum_repos([{"base_url": generate_string_of_length(0)}])
    validate_correct_yum_repos([{"base_url": generate_string_of_length(2048)}])
    validate_incorrect_value(yum_repos, [{"base_url": generate_string_of_length(2049)}])
    for value_s in INCORRECT_STRING_VALUES:
        validate_incorrect_value(yum_repos, [{"base_url": value_s}])

    # mirrorlist
    validate_correct_yum_repos([{"mirrorlist": generate_string_of_length(0)}])
    validate_correct_yum_repos([{"mirrorlist": generate_string_of_length(2048)}])
    validate_incorrect_value(yum_repos, [{"mirrorlist": generate_string_of_length(2049)}])
    for value_s in INCORRECT_STRING_VALUES:
        validate_incorrect_value(yum_repos, [{"mirrorlist": value_s}])

    # gpgcheck
    validate_correct_yum_repos([{"gpgcheck": True}])
    validate_correct_yum_repos([{"gpgcheck": False}])
    for value_b in INCORRECT_BOOLEAN_VALUES:
        validate_incorrect_value(yum_repos, [{"gpgcheck": value_b}])

    # enabled
    validate_correct_yum_repos([{"enabled": True}])
    validate_correct_yum_repos([{"enabled": False}])
    for value_b in INCORRECT_BOOLEAN_VALUES:
        validate_incorrect_value(yum_repos, [{"enabled": value_b}])

    correct_yum_repo = {
        "id": "123",
        "name": "test",
        "gpgcheck": True,
        "enabled": False,
        "base_url": "http://localhost",
        "mirrorlist": mirrorlist,
    }
    incorrect_yum_repo = {**correct_yum_repo, "id": generate_string_of_length(257)}
    validate_correct_yum_repos([])
    validate_correct_yum_repos([{}])
    validate_correct_yum_repos([correct_yum_repo])
    validate_correct_yum_repos([correct_yum_repo for _ in range(10)])
    validate_incorrect_value(yum_repos, [incorrect_yum_repo])
    validate_incorrect_value(
        yum_repos, [correct_yum_repo for _ in range(10)] + [incorrect_yum_repo]
    )


@pytest.mark.ephemeral
def test_validate_system_profile_dnf_modules(
    validate_correct_dnf_modules, validate_incorrect_value
):
    """
    Test validation of system_profile dnf_modules field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile dnf_modules field
    """

    dnf_modules = get_sp_field_by_name("dnf_modules")
    # name
    validate_correct_dnf_modules([{"name": generate_string_of_length(0)}])
    validate_correct_dnf_modules([{"name": generate_string_of_length(128)}])
    validate_incorrect_value(dnf_modules, [{"name": generate_string_of_length(129)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(dnf_modules, [{"name": value}])

    # stream
    validate_correct_dnf_modules([{"stream": generate_string_of_length(0)}])
    validate_correct_dnf_modules([{"stream": generate_string_of_length(2048)}])
    validate_incorrect_value(dnf_modules, [{"stream": generate_string_of_length(2049)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(dnf_modules, [{"stream": value}])

    correct_dnf_module = {"name": "test", "stream": "test_stream"}
    incorrect_dnf_module = deepcopy(correct_dnf_module)
    incorrect_dnf_module["name"] = generate_string_of_length(129)
    validate_correct_dnf_modules([])
    validate_correct_dnf_modules([{}])
    validate_correct_dnf_modules([correct_dnf_module])
    validate_correct_dnf_modules([correct_dnf_module for _ in range(10)])
    validate_incorrect_value(dnf_modules, [incorrect_dnf_module])
    validate_incorrect_value(
        dnf_modules, [correct_dnf_module for _ in range(10)] + [incorrect_dnf_module]
    )


@pytest.mark.ephemeral
def test_validate_system_profile_installed_products(
    validate_correct_installed_products, validate_incorrect_value
):
    """
    Test validation of system_profile installed_products field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile installed_products field
    """
    installed_products = get_sp_field_by_name("installed_products")
    # name
    validate_correct_installed_products([{"name": generate_string_of_length(0)}])
    validate_correct_installed_products([{"name": generate_string_of_length(512)}])
    validate_incorrect_value(installed_products, [{"name": generate_string_of_length(513)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(installed_products, [{"name": value}])

    # id
    validate_correct_installed_products([{"id": generate_string_of_length(0)}])
    validate_correct_installed_products([{"id": generate_string_of_length(64)}])
    validate_incorrect_value(installed_products, [{"id": generate_string_of_length(65)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(installed_products, [{"id": value}])

    # status
    validate_correct_installed_products([{"status": generate_string_of_length(0)}])
    validate_correct_installed_products([{"status": generate_string_of_length(256)}])
    validate_incorrect_value(installed_products, [{"status": generate_string_of_length(257)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(installed_products, [{"status": value}])

    correct_installed_product = {"name": "test", "id": "71", "status": "Subscribed"}
    incorrect_installed_product = deepcopy(correct_installed_product)
    incorrect_installed_product["name"] = generate_string_of_length(513)
    validate_correct_installed_products([])
    validate_correct_installed_products([{}])
    validate_correct_installed_products([correct_installed_product])
    validate_correct_installed_products([correct_installed_product for _ in range(10)])
    validate_incorrect_value(installed_products, [incorrect_installed_product])
    validate_incorrect_value(
        installed_products,
        [correct_installed_product] * 10 + [incorrect_installed_product],
    )


@pytest.mark.ephemeral
def test_validate_system_profile_network_interfaces(
    validate_correct_network_interfaces, validate_incorrect_value
):
    """
    Test validation of system_profile network_interfaces field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile network_interfaces field
    """
    network_interfaces = get_sp_field_by_name("network_interfaces")
    # mac_address
    validate_correct_network_interfaces([{"mac_address": generate_macs(1)[0]}])
    validate_correct_network_interfaces([{"mac_address": generate_macs(1)[0].replace(":", "-")}])
    validate_correct_network_interfaces([{"mac_address": generate_macs(1)[0].replace(":", "")}])
    validate_correct_network_interfaces([{"mac_address": "0123.4567.89ab"}])
    for value in INCORRECT_MAC_ADDRESSES:
        validate_incorrect_value(network_interfaces, [{"mac_address": value}])

    # name
    validate_incorrect_value(network_interfaces, [{"name": generate_string_of_length(0)}])
    validate_correct_network_interfaces([{"name": generate_string_of_length(1)}])
    validate_correct_network_interfaces([{"name": generate_string_of_length(50)}])
    validate_incorrect_value(network_interfaces, [{"name": generate_string_of_length(51)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(network_interfaces, [{"name": value}])

    # state
    validate_correct_network_interfaces([{"state": generate_string_of_length(0)}])
    validate_correct_network_interfaces([{"state": generate_string_of_length(25)}])
    validate_incorrect_value(network_interfaces, [{"state": generate_string_of_length(26)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(network_interfaces, [{"state": value}])

    # type
    validate_correct_network_interfaces([{"type": generate_string_of_length(0)}])
    validate_correct_network_interfaces([{"type": generate_string_of_length(18)}])
    validate_incorrect_value(network_interfaces, [{"type": generate_string_of_length(19)}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(network_interfaces, [{"type": value}])

    # mtu
    # TU_INT_MAX = 2147483647  # copied from sp fields generator

    validate_correct_network_interfaces([{"mtu": 0}])

    warnings.warn("leaving out max mtu tests due to integer size xjoin vs db", stacklevel=1)
    # validate_correct_network_interfaces([{"mtu": MTU_INT_MAX}])
    # validate_incorrect_value(network_interfaces, [{"mtu": MTU_INT_MAX + 1}])
    validate_incorrect_value(network_interfaces, [{"mtu": -1}])
    validate_incorrect_value(network_interfaces, [{"mtu": 12.5}])
    validate_incorrect_value(network_interfaces, [{"mtu": [123]}])
    for value in INCORRECT_INTEGER_VALUES:
        validate_incorrect_value(network_interfaces, [{"mtu": value}])

    # ipv4_addresses
    validate_correct_network_interfaces([{"ipv4_addresses": []}])
    validate_correct_network_interfaces([{"ipv4_addresses": generate_ips(1)}])
    validate_correct_network_interfaces([{"ipv4_addresses": generate_ips(10)}])
    validate_incorrect_value(network_interfaces, [{"ipv4_addresses": generate_ips()[0]}])

    # ipv6_addresses
    validate_correct_network_interfaces([{"ipv6_addresses": []}])
    validate_correct_network_interfaces([{"ipv6_addresses": generate_ipv6s(1)}])
    validate_correct_network_interfaces([{"ipv6_addresses": generate_ipv6s(10)}])
    validate_incorrect_value(network_interfaces, [{"ipv6_addresses": generate_ipv6s()[0]}])

    correct_network_interface = {
        "ipv4_addresses": ["64.233.161.147"],
        "ipv6_addresses": ["0123:4567:89ab:cdef:0123:4567:89ab:cdef"],
        "mtu": 1234,
        "mac_address": "00:00:00:00:00:00",
        "name": "eth0",
        "state": "UP",
        "type": "ether",
    }
    incorrect_network_interface = deepcopy(correct_network_interface)
    incorrect_network_interface["name"] = generate_string_of_length(51)
    validate_correct_network_interfaces([])
    validate_correct_network_interfaces([{}])
    validate_correct_network_interfaces([correct_network_interface])
    validate_correct_network_interfaces([correct_network_interface for _ in range(10)])
    validate_incorrect_value(network_interfaces, [incorrect_network_interface])
    validate_incorrect_value(
        network_interfaces,
        [correct_network_interface for _ in range(10)] + [incorrect_network_interface],
    )


@pytest.mark.ephemeral
def test_validate_system_profile_operating_system(
    validate_correct_value, validate_incorrect_value
):
    """
    Test validation of system_profile operating_system field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile operating_system field
    """
    correct_operating_system = {
        "major": 6,
        "minor": 8,
        "name": "RHEL",
    }

    operating_system = get_sp_field_by_name("operating_system")

    def _test_int_value(field_name):
        tested_value = deepcopy(correct_operating_system)
        tested_value[field_name] = 0
        validate_correct_value(operating_system, tested_value)
        tested_value[field_name] = 99
        validate_correct_value(operating_system, tested_value)
        tested_value[field_name] = 100
        validate_incorrect_value(operating_system, tested_value)
        for value in INCORRECT_INTEGER_VALUES:
            tested_value[field_name] = value
            validate_incorrect_value(operating_system, tested_value)

    _test_int_value("major")
    _test_int_value("minor")

    # name
    tested_value = deepcopy(correct_operating_system)
    tested_value["name"] = "RHEL"
    validate_correct_value(operating_system, tested_value)
    tested_value["name"] = "CentOS"
    validate_correct_value(operating_system, tested_value)
    tested_value["name"] = ""
    validate_incorrect_value(operating_system, tested_value)
    tested_value["name"] = "RHEI"
    validate_incorrect_value(operating_system, tested_value)
    tested_value["name"] = "centos"
    validate_incorrect_value(operating_system, tested_value)
    for value in INCORRECT_STRING_VALUES:
        tested_value["name"] = value
        validate_incorrect_value(operating_system, tested_value)

    validate_correct_value(operating_system, correct_operating_system)
    incorrect_operating_system = deepcopy(correct_operating_system)
    incorrect_operating_system.pop("major")
    validate_incorrect_value(operating_system, incorrect_operating_system)
    incorrect_operating_system = deepcopy(correct_operating_system)
    incorrect_operating_system.pop("minor")
    validate_incorrect_value(operating_system, incorrect_operating_system)
    incorrect_operating_system = deepcopy(correct_operating_system)
    incorrect_operating_system.pop("name")
    validate_incorrect_value(operating_system, incorrect_operating_system)
    validate_incorrect_value(operating_system, {})
    validate_incorrect_value(operating_system, [correct_operating_system])


@pytest.mark.ephemeral
def test_validate_system_profile_rhsm(validate_correct_rhsm, validate_incorrect_value):
    """
    Test validation of system_profile rhsm field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile rhsm field
    """
    rhsm = get_sp_field_by_name("rhsm")

    # version
    validate_correct_rhsm({"version": generate_string_of_length(0)})
    validate_correct_rhsm({"version": generate_string_of_length(255)})
    validate_incorrect_value(rhsm, {"version": generate_string_of_length(256)})
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(rhsm, {"version": value})

    # environment_ids
    validate_correct_rhsm({"environment_ids": [generate_string_of_length(0)]})
    validate_correct_rhsm({"environment_ids": [generate_string_of_length(256)]})
    validate_incorrect_value(rhsm, {"environment_ids": [generate_string_of_length(257)]})
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(rhsm, {"environment_ids": [value]})
    validate_correct_rhsm({"environment_ids": [generate_string_of_length(0) for _ in range(50)]})
    validate_incorrect_value(rhsm, {"environment_ids": generate_string_of_length(32)})

    # both
    validate_correct_rhsm({
        "version": generate_string_of_length(10),
        "environment_ids": [generate_string_of_length(10)],
    })

    # TODO: Investigate why sending a list is allowed
    # validate_incorrect_value(
    #     rhsm,
    #     [
    #         {
    #             "version": generate_string_of_length(10),
    #             "environment_ids": [generate_string_of_length(10)],
    #         }
    #     ],
    # )


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", ["3.10.0", "3.10.0.5", "12345.67890.12345.67"])
def test_validate_system_profile_os_kernel_version_correct(validate_correct_value, value):
    """
    Test correct values for system_profile os_kernel_version field

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile os_kernel_version field
    """
    validate_correct_value(get_sp_field_by_name("os_kernel_version"), value)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "value",
    [
        *EMPTY_BASICS,
        ["3.10.0"],
        "12345.67890.12345.678",
        "3,10,5",
        "3.10.5.",
        "3.10.",
        "3.10",
        pytest.param(generate_digits(10), id="10 digits"),
    ],
)
def test_validate_system_profile_os_kernel_version_incorrect(validate_incorrect_value, value):
    """
    Test incorrect values for system_profile os_kernel_version field

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile os_kernel_version field
    """
    validate_incorrect_value(get_sp_field_by_name("os_kernel_version"), value)


@pytest.mark.ephemeral
def test_validate_system_profile_sap(validate_correct_workloads, validate_incorrect_value):
    """
    Test validation of system_profile sap field

    https://issues.redhat.com/browse/ESSNTL-1616

    metadata:
        assignee: zabikeno
        importance: high
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile sap field
    """
    workloads = get_sp_field_by_name("workloads")

    def _test_property(name: str, correct_values, incorrect_values) -> None:
        for value in correct_values:
            validate_correct_workloads({"sap": {name: value}})
        for value in incorrect_values:
            validate_incorrect_value(workloads, {"sap": {name: value}})

    _test_property("sids", CORRECT_SAP_SIDS, INCORRECT_SAP_SIDS)
    _test_property("instance_number", CORRECT_SAP_INSTANCE_NUMBER, INCORRECT_SAP_INSTANCE_NUMBER)
    _test_property("version", CORRECT_SAP_VERSION, INCORRECT_SAP_VERSION)
    _test_property("sap_system", [True, False], INCORRECT_BOOLEAN_VALUES)

    correct_sap = {
        "sap_system": True,
        "sids": ["H2O"],
        "instance_number": "03",
        "version": "1.00.122.04.1478575636",
    }

    validate_correct_workloads({"sap": {}})
    validate_correct_workloads({"sap": correct_sap})

    incorrect_sap = deepcopy(correct_sap)
    incorrect_sap["sids"] = ["A!"]
    validate_incorrect_value(workloads, {"sap": incorrect_sap})
    validate_incorrect_value(workloads, [{"sap": correct_sap}])


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", CORRECT_SAP_SIDS)
def test_validate_system_profile_sap_sids_correct(validate_correct_value, value):
    """
    Test validation of system_profile sap_sids field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile sap_sids field
    """
    # TODO: Remove when sap_sids field https://issues.redhat.com/browse/ESSNTL-3765
    field = get_sp_field_by_name("sap_sids")
    validate_correct_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", INCORRECT_SAP_SIDS)
def test_validate_system_profile_sap_sids_incorrect(validate_incorrect_value, value):
    """
    Test validation of system_profile sap_sids field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile sap_sids field
    """
    # TODO: Remove when sap_sids field https://issues.redhat.com/browse/ESSNTL-3765
    field = get_sp_field_by_name("sap_sids")
    validate_incorrect_value(field, value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", CORRECT_SAP_INSTANCE_NUMBER)
def test_validate_system_profile_sap_instance_number_correct(validate_correct_value, value):
    """
    Test correct values for system_profile sap_instance_number field

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile sap_instance_number field
    """
    # TODO: Remove when sap_instance_number field https://issues.redhat.com/browse/ESSNTL-3765
    validate_correct_value(get_sp_field_by_name("sap_instance_number"), value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", INCORRECT_SAP_INSTANCE_NUMBER)
def test_validate_system_profile_sap_instance_number_incorrect(validate_incorrect_value, value):
    """
    Test incorrect values for system_profile sap_instance_number field

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile sap_instance_number field
    """
    # TODO: Remove when sap_instance_number field https://issues.redhat.com/browse/ESSNTL-3765
    validate_incorrect_value(get_sp_field_by_name("sap_instance_number"), value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", CORRECT_SAP_VERSION)
def test_validate_system_profile_sap_version_correct(validate_correct_value, value):
    """
    Test correct values for system_profile sap_version field

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-create
        title: Validation of correct values in system_profile sap_version field
    """
    # TODO: Remove when sap_version field https://issues.redhat.com/browse/ESSNTL-3765
    validate_correct_value(get_sp_field_by_name("sap_version"), value)


@pytest.mark.ephemeral
@pytest.mark.parametrize("value", INCORRECT_SAP_VERSION)
def test_validate_system_profile_sap_version_incorrect(validate_incorrect_value, value):
    """
    Test incorrect values for system_profile sap_version field

    metadata:
        assignee: fstavela
        importance: low
        requirements: inv-mq-host-field-validation
        negative: true
        title: Validation of incorrect values in system_profile sap_version field
    """
    # TODO: Remove when sap_version field https://issues.redhat.com/browse/ESSNTL-3765
    validate_incorrect_value(get_sp_field_by_name("sap_version"), value)


@pytest.mark.ephemeral
def test_validate_system_profile_rpm_ostree_deployments(
    validate_correct_value, validate_incorrect_value
):
    """Test validation of system_profile rpm_ostree_deployments field

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile rpm_ostree_deployments field
    """
    field = get_sp_field_by_name("rpm_ostree_deployments")
    correct_rpm_ostree_deployment = {
        "id": "fedora-63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb.0",
        "checksum": "63335a77f9853618ba1a5f139c5805e82176a2a040ef5e34d7402e12263af5bb",
        "origin": "fedora/33/x86_64/silverblue",
        "osname": "fedora-silverblue",
        "version": "33.21",
        "booted": True,
        "pinned": False,
    }

    def _test_string_field(name, min_len, max_len):
        tested_rpm_ostree_deployment = deepcopy(correct_rpm_ostree_deployment)
        if min_len != 0:
            tested_rpm_ostree_deployment[name] = generate_string_of_length(min_len - 1)
            validate_incorrect_value(field, [tested_rpm_ostree_deployment])
        tested_rpm_ostree_deployment[name] = generate_string_of_length(min_len)
        validate_correct_value(field, [tested_rpm_ostree_deployment])
        tested_rpm_ostree_deployment[name] = generate_string_of_length(max_len)
        validate_correct_value(field, [tested_rpm_ostree_deployment])
        tested_rpm_ostree_deployment[name] = generate_string_of_length(max_len + 1)
        validate_incorrect_value(field, [tested_rpm_ostree_deployment])
        for value in INCORRECT_STRING_VALUES:
            tested_rpm_ostree_deployment[name] = value
            validate_incorrect_value(field, [tested_rpm_ostree_deployment])

    def _test_boolean_field(name):
        tested_rpm_ostree_deployment = deepcopy(correct_rpm_ostree_deployment)
        tested_rpm_ostree_deployment[name] = True
        validate_correct_value(field, [tested_rpm_ostree_deployment])
        tested_rpm_ostree_deployment[name] = False
        validate_correct_value(field, [tested_rpm_ostree_deployment])
        for value in INCORRECT_BOOLEAN_VALUES:
            tested_rpm_ostree_deployment[name] = value
            validate_incorrect_value(field, [tested_rpm_ostree_deployment])

    _test_string_field("id", 1, 255)
    _test_string_field("origin", 0, 255)
    _test_string_field("osname", 1, 255)
    _test_string_field("version", 1, 255)
    _test_boolean_field("booted")
    _test_boolean_field("pinned")

    # Test checksum
    incorrect_rpm_ostree_deployment = deepcopy(correct_rpm_ostree_deployment)
    incorrect_rpm_ostree_deployment["checksum"] = generate_string_of_length(64)
    validate_incorrect_value(field, [incorrect_rpm_ostree_deployment])
    incorrect_rpm_ostree_deployment["checksum"] = token_hex(31)
    validate_incorrect_value(field, [incorrect_rpm_ostree_deployment])
    incorrect_rpm_ostree_deployment["checksum"] = token_hex(33)
    validate_incorrect_value(field, [incorrect_rpm_ostree_deployment])
    correct_rpm_ostree_deployment["checksum"] = token_hex(32)
    validate_correct_value(field, [correct_rpm_ostree_deployment])

    # Test that all fields except version are required
    for key in correct_rpm_ostree_deployment:
        if key == "version":
            continue
        incorrect_rpm_ostree_deployment = deepcopy(correct_rpm_ostree_deployment)
        del incorrect_rpm_ostree_deployment[key]
        validate_incorrect_value(field, [incorrect_rpm_ostree_deployment])

    incorrect_rpm_ostree_deployment = deepcopy(correct_rpm_ostree_deployment)
    incorrect_rpm_ostree_deployment["id"] = generate_string_of_length(257)
    validate_correct_value(field, [])
    validate_correct_value(field, [correct_rpm_ostree_deployment])
    validate_correct_value(field, [correct_rpm_ostree_deployment for _ in range(10)])
    validate_incorrect_value(field, [{}])
    validate_incorrect_value(
        field,
        [correct_rpm_ostree_deployment for _ in range(10)] + [incorrect_rpm_ostree_deployment],
    )


@pytest.mark.ephemeral
def test_validate_system_profile_ansible(validate_correct_workloads, validate_incorrect_value):
    """
    Test validation of system_profile ansible field

    https://issues.redhat.com/browse/ESSNTL-1423

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile ansible field
    """

    workloads = get_sp_field_by_name("workloads")

    def _test_property(name):
        validate_correct_workloads({"ansible": {name: "0.0"}})
        validate_correct_workloads({"ansible": {name: "9.9"}})
        validate_correct_workloads({"ansible": {name: "0.1.2.3.4.5.6.7.8.9.0.1.2.3.4"}})
        validate_correct_workloads({
            "ansible": {name: f"{generate_digits(28)}.{generate_digits(1)}"}
        })
        validate_correct_workloads({
            "ansible": {name: f"{generate_digits(1)}.{generate_digits(28)}"}
        })
        validate_correct_workloads({
            "ansible": {name: ".".join([generate_digits(i + 1) for i in range(5)])}
        })
        validate_incorrect_value(workloads, {"ansible": {name: ""}})
        validate_incorrect_value(workloads, {"ansible": {name: "."}})
        validate_incorrect_value(workloads, {"ansible": {name: "0"}})
        validate_incorrect_value(workloads, {"ansible": {name: "123"}})
        validate_incorrect_value(workloads, {"ansible": {name: ".0"}})
        validate_incorrect_value(workloads, {"ansible": {name: "0."}})
        validate_incorrect_value(workloads, {"ansible": {name: "0.0."}})
        validate_incorrect_value(workloads, {"ansible": {name: ".0.0"}})
        validate_incorrect_value(workloads, {"ansible": {name: "0.a"}})
        validate_incorrect_value(workloads, {"ansible": {name: "0.A"}})
        validate_incorrect_value(workloads, {"ansible": {name: "0.$"}})
        validate_incorrect_value(workloads, {"ansible": {name: "0.1.2.3.4.5.6.7.8.9.0.1.2.3.4.5"}})
        validate_incorrect_value(workloads, {"ansible": {name: "0.1.2.3.4.5.6.7.8.9.0.1.2.3.400"}})
        validate_incorrect_value(
            workloads, {"ansible": {name: f"{generate_digits(29)}.{generate_digits(1)}"}}
        )
        for value in INCORRECT_STRING_VALUES:
            validate_incorrect_value(workloads, {"ansible": {name: value}})

    _test_property("controller_version")
    _test_property("hub_version")
    _test_property("catalog_worker_version")
    _test_property("sso_version")

    correct_ansible = {
        "controller_version": "1.2.3",
        "hub_version": "4.5.6",
        "catalog_worker_version": "7.8.9",
        "sso_version": "10.11.12",
    }
    incorrect_ansible = deepcopy(correct_ansible)
    incorrect_ansible["controller_version"] = "4."
    validate_correct_workloads({"ansible": {}})
    validate_correct_workloads({"ansible": correct_ansible})
    validate_incorrect_value(workloads, {"ansible": incorrect_ansible})
    validate_incorrect_value(workloads, [{"ansible": correct_ansible}])


@pytest.mark.ephemeral
def test_validate_system_profile_system_purpose(
    validate_correct_system_purpose, validate_incorrect_value
):
    """
    Test validation of system_profile system_purpose field

    https://issues.redhat.com/browse/ESSNTL-1513

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile system_purpose field
    """
    system_purpose = get_sp_field_by_name("system_purpose")

    def _test_property(name: str, correct_values) -> None:
        for value in correct_values:
            validate_correct_system_purpose({name: value})
        for value in INCORRECT_STRING_VALUES:
            validate_incorrect_value(system_purpose, {name: value})

    _test_property("usage", ["Production", "Development/Test", "Disaster Recovery"])
    _test_property(
        "role",
        [
            "Red Hat Enterprise Linux Server",
            "Red Hat Enterprise Linux Workstation",
            "Red Hat Enterprise Linux Compute Node",
        ],
    )
    _test_property("sla", ["Premium", "Standard", "Self-Support"])

    correct_system_purpose = {
        "usage": "Production",
        "role": "Red Hat Enterprise Linux Server",
        "sla": "Premium",
    }
    validate_correct_system_purpose({})
    validate_correct_system_purpose(correct_system_purpose)
    validate_incorrect_value(system_purpose, [correct_system_purpose])


@pytest.mark.ephemeral
def test_validate_system_profile_mssql(validate_correct_workloads, validate_incorrect_value):
    """
    Test validation of system_profile mssql field

    https://issues.redhat.com/browse/ESSNTL-1612

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile mssql field
    """

    workloads = get_sp_field_by_name("workloads")
    validate_correct_workloads({"mssql": {}})
    validate_correct_workloads({"mssql": {"version": ""}})
    validate_correct_workloads({"mssql": {"version": "15.2.0"}})
    validate_correct_workloads({"mssql": {"version": generate_string_of_length(30)}})
    validate_incorrect_value(workloads, {"mssql": {"version": generate_string_of_length(31)}})
    validate_incorrect_value(workloads, [{"mssql": {"version": "15.2.0"}}])
    for value in INCORRECT_STRING_VALUES:
        validate_incorrect_value(workloads, {"mssql": {"version": value}})


@pytest.mark.ephemeral
def test_validate_system_profile_systemd(validate_correct_value, validate_incorrect_value):
    """
    Test validation of system_profile systemd field

    https://issues.redhat.com/browse/RHINENG-492

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile systemd field
    """
    correct_systemd = {
        "failed": 1,
        "jobs_queued": 4,
        "state": "running",
        "failed_services": ["ex1", "ex2"],
    }
    correct_states = ["initializing", "starting", "running", "degraded", "maintenance", "stopping"]

    systemd = get_sp_field_by_name("systemd")

    def _test_int_value(field_name):
        tested_value = deepcopy(correct_systemd)
        tested_value[field_name] = 0
        validate_correct_value(systemd, tested_value)
        tested_value[field_name] = 2147483647
        validate_correct_value(systemd, tested_value)
        tested_value[field_name] = -1
        validate_incorrect_value(systemd, tested_value)
        for value in INCORRECT_INTEGER_VALUES:
            tested_value[field_name] = value
            validate_incorrect_value(systemd, tested_value)

    _test_int_value("failed")
    _test_int_value("jobs_queued")

    # state
    tested_value = deepcopy(correct_systemd)
    for state in correct_states:
        tested_value["state"] = state
        validate_correct_value(systemd, tested_value)

    tested_value["state"] = ""
    validate_incorrect_value(systemd, tested_value)
    tested_value["state"] = "start"
    validate_incorrect_value(systemd, tested_value)
    for value in INCORRECT_STRING_VALUES:
        tested_value["state"] = value
        validate_incorrect_value(systemd, tested_value)

    # failed_services
    tested_value = deepcopy(correct_systemd)
    tested_value.pop("failed_services")  # failed_services is not required
    expected_value = normalize_object(list(correct_systemd.keys()), tested_value)
    validate_correct_value(systemd, tested_value, expected_value)
    tested_value["failed_services"] = ["a"]
    validate_correct_value(systemd, tested_value)
    tested_value["failed_services"] = [generate_string_of_length(1000)]
    validate_correct_value(systemd, tested_value)
    tested_value["failed_services"] = [generate_string_of_length(100) for _ in range(100)]
    validate_correct_value(systemd, tested_value)

    tested_value["failed_services"] = [generate_string_of_length(1001)]
    validate_incorrect_value(systemd, tested_value)
    tested_value["failed_services"] = "a"
    validate_incorrect_value(systemd, tested_value)
    tested_value["failed_services"] = [["a"]]
    validate_incorrect_value(systemd, tested_value)

    validate_correct_value(systemd, correct_systemd)
    incorrect_systemd = deepcopy(correct_systemd)
    incorrect_systemd.pop("failed")
    validate_incorrect_value(systemd, incorrect_systemd)
    incorrect_systemd = deepcopy(correct_systemd)
    incorrect_systemd.pop("jobs_queued")
    validate_incorrect_value(systemd, incorrect_systemd)
    incorrect_systemd = deepcopy(correct_systemd)
    incorrect_systemd.pop("state")
    validate_incorrect_value(systemd, incorrect_systemd)
    validate_incorrect_value(systemd, {})
    validate_incorrect_value(systemd, [correct_systemd])


@pytest.mark.ephemeral
def test_validate_system_profile_bootc_status(
    validate_correct_bootc_status, validate_incorrect_value
):
    """
    Test validation of system_profile bootc_status field

    https://issues.redhat.com/browse/RHINENG-8986

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile bootc_status field
    """
    correct_bootc_status = {
        "booted": {
            "image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
            "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
            "cached_image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
            "cached_image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
        },
        "rollback": {
            "image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
            "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
            "cached_image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
            "cached_image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
        },
        "staged": {
            "image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
            "image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
            "cached_image": "quay.io/centos-bootc/fedora-bootc-cloud:eln",
            "cached_image_digest": "sha256:806d77394f96e47cf99b1233561ce970c94521244a2d8f2affa12c3261961223",  # noqa: E501
        },
    }

    bootc_status = get_sp_field_by_name("bootc_status")

    def _test_image(field_name: str):
        for subfield_name in ("image", "cached_image"):
            tested_bootc_status = deepcopy(correct_bootc_status)

            tested_bootc_status[field_name][subfield_name] = ""  # min length
            validate_correct_bootc_status(tested_bootc_status)
            tested_bootc_status[field_name][subfield_name] = generate_string_of_length(
                128
            )  # max length
            validate_correct_bootc_status(tested_bootc_status)

            tested_bootc_status[field_name][subfield_name] = generate_string_of_length(
                129
            )  # too long
            validate_incorrect_value(bootc_status, tested_bootc_status)

            for value in INCORRECT_STRING_VALUES:
                tested_bootc_status[field_name][subfield_name] = _unpack_param(value)
                validate_incorrect_value(bootc_status, tested_bootc_status)

    def _test_image_digest(field_name: str):
        for subfield_name in ("image_digest", "cached_image_digest"):
            tested_bootc_status = deepcopy(correct_bootc_status)

            tested_bootc_status[field_name][subfield_name] = f"sha256:{token_hex(32)}"
            validate_correct_bootc_status(tested_bootc_status)

            tested_bootc_status[field_name][subfield_name] = generate_string_of_length(71)
            validate_incorrect_value(bootc_status, tested_bootc_status)
            tested_bootc_status[field_name][subfield_name] = f"sha256:{token_hex(31)}"
            validate_incorrect_value(bootc_status, tested_bootc_status)
            tested_bootc_status[field_name][subfield_name] = f"sha256:{token_hex(33)}"
            validate_incorrect_value(bootc_status, tested_bootc_status)
            tested_bootc_status[field_name][subfield_name] = f"sha255:{token_hex(32)}"
            validate_incorrect_value(bootc_status, tested_bootc_status)
            tested_bootc_status[field_name][subfield_name] = token_hex(32)
            validate_incorrect_value(bootc_status, tested_bootc_status)
            tested_bootc_status[field_name][subfield_name] = f"sha256:{token_hex(31)}fg"
            validate_incorrect_value(bootc_status, tested_bootc_status)

            for value in INCORRECT_STRING_VALUES:
                tested_bootc_status[field_name][subfield_name] = _unpack_param(value)
                validate_incorrect_value(bootc_status, tested_bootc_status)

    def _test_subfields_optional(field_name: str):
        """Test that all nested sub-fields are optional"""
        tested_bootc_status = deepcopy(correct_bootc_status)
        tested_bootc_status[field_name] = {}
        validate_correct_bootc_status(tested_bootc_status)

    for subfield in correct_bootc_status.keys():
        _test_image(subfield)
        _test_image_digest(subfield)
        _test_subfields_optional(subfield)

    validate_correct_bootc_status({})  # All fields are optional
    validate_correct_bootc_status(correct_bootc_status)
    validate_incorrect_value(bootc_status, [correct_bootc_status])


@pytest.mark.ephemeral
def test_validate_system_profile_conversions(
    validate_correct_conversions, validate_incorrect_value
):
    """
    Test validation of system_profile conversions field

    https://github.com/RedHatInsights/insights-host-inventory/pull/1720/files

    metadata:
        assignee: fstavela
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile conversions field
    """

    conversions = get_sp_field_by_name("conversions")
    validate_correct_conversions({})
    validate_correct_conversions({"activity": True})
    validate_correct_conversions({"activity": False})
    validate_incorrect_value(conversions, {"activity": ""})
    validate_incorrect_value(conversions, {"activity": generate_string_of_length(4)})
    validate_incorrect_value(conversions, [{"activity": True}])
    for value in INCORRECT_BOOLEAN_VALUES:
        validate_incorrect_value(conversions, {"activity": value})


@pytest.mark.ephemeral
def test_validate_system_profile_rhel_ai(validate_correct_rhel_ai, validate_incorrect_value):
    """
    Test validation of system_profile rhel_ai field

    https://issues.redhat.com/browse/RHINENG-14894

    metadata:
        assignee: zabikeno
        importance: medium
        requirements: inv-mq-host-field-validation, inv-host-create
        title: Validation of system_profile rhel_ai field
    """
    rhel_ai = get_sp_field_by_name("rhel_ai")

    correct_rhel_ai = {
        "variant": "RHEL AI",
        "rhel_ai_version_id": "v1.1.3",
        "nvidia_gpu_models": ["NVIDIA T1000", "Tesla V100-PCIE-16GB"],
        "intel_gaudi_hpu_models": [
            "Habana Labs Ltd. Device 1020",
            "Habana Labs Ltd. HL-2000 AI Training Accelerator [Gaudi]",
        ],
        "amd_gpu_models": [
            "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34",
            "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34",
        ],
    }
    validate_correct_rhel_ai(correct_rhel_ai)

    def _test_property(name: str, correct_values: list, incorrect_values: list) -> None:
        tested_rhel_ai = deepcopy(correct_rhel_ai)
        for value in correct_values:
            tested_rhel_ai[name] = value
            validate_correct_rhel_ai(tested_rhel_ai)
        for value in incorrect_values:
            tested_rhel_ai[name] = value
            validate_incorrect_value(rhel_ai, tested_rhel_ai)

    _test_property(
        "rhel_ai_version_id",
        [generate_string_of_length(0), generate_string_of_length(16)],
        [generate_string_of_length(1025), 111],
    )
    _test_property(
        "variant",
        [generate_string_of_length(0), generate_string_of_length(7)],
        [generate_string_of_length(1025), 111],
    )

    CORRECT_SUBFIELD_VALUES = [
        [],
        [generate_string_of_length(1, 128)],
        [generate_string_of_length(1, 128), generate_string_of_length(1, 100)],
    ]
    INCORRECT_SUBFIELD_VALUES = [[1], generate_string_of_length(1, 100), {}]
    _test_property("nvidia_gpu_models", CORRECT_SUBFIELD_VALUES, INCORRECT_SUBFIELD_VALUES)
    _test_property("amd_gpu_models", CORRECT_SUBFIELD_VALUES, INCORRECT_SUBFIELD_VALUES)
    _test_property("intel_gaudi_hpu_models", CORRECT_SUBFIELD_VALUES, INCORRECT_SUBFIELD_VALUES)
