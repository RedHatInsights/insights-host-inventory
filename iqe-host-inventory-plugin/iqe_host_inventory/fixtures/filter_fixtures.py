import datetime
import logging
from random import randint

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.kafka_interaction import SAP_FILTER_TAG
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.test_filter_hosts import FILTER_OS_DISPLAY_NAME
from iqe_host_inventory.utils.api_utils import delete_hosts_by_tags
from iqe_host_inventory.utils.datagen_utils import _CORRECT_REGISTERED_WITH_VALUES
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import generate_operating_system
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_timestamp
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.upload_utils import get_archive_and_collect_method
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import HostsApi
from iqe_host_inventory_api import StructuredTag
from iqe_host_inventory_api import TagsApi

logger = logging.getLogger(__name__)


def build_query(field_name, value, comparator=None) -> str:
    return (
        f"[{field_name}][{comparator}]={value}"
        if comparator is not None
        else f"[{field_name}]={value}"
    )


@pytest.fixture
def filter_hosts(host_inventory: ApplicationHostInventory):
    def _filter(field_name, value, comparator=None):
        return host_inventory.apis.hosts.get_hosts_response(
            filter=[build_query(field_name, value, comparator)]
        )

    yield _filter


@pytest.fixture
def filter_tags(host_inventory: ApplicationHostInventory):
    def _filter(field_name, value, comparator=None):
        return host_inventory.apis.tags.get_tags_response(
            filter=[build_query(field_name, value, comparator)]
        )

    yield _filter


@pytest.fixture
def setup_string_hosts_for_string_filtering(host_inventory: ApplicationHostInventory):
    def _gen_string(min_l: int, max_l: int) -> str:
        # https://issues.redhat.com/browse/ESSNTL-3918
        return generate_string_of_length(min_l + 10, max_l).replace("\\", "")

    def _setup_hosts(field: Field):
        min_len = field.min_len
        max_len = field.max_len
        assert min_len is not None
        assert max_len is not None
        hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
        hosts_data[0]["system_profile"][field.name] = _gen_string(min_len, max_len)
        hosts_data[1]["system_profile"][field.name] = _gen_string(min_len, max_len)
        if min_len == 0:
            hosts_data[2]["system_profile"][field.name] = ""
            hosts_data.append(host_inventory.datagen.create_host_data_with_tags())
        hosts_data[-1]["system_profile"].pop(field.name, None)
        return host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    yield _setup_hosts


@pytest.fixture
def setup_uuid_hosts_for_string_filtering(host_inventory: ApplicationHostInventory):
    def _setup_hosts(field: Field):
        name = field.name
        hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
        hosts_data[0]["system_profile"][name] = generate_uuid()
        hosts_data[1]["system_profile"][name] = generate_uuid()
        hosts_data[2]["system_profile"].pop(name, None)
        return host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    yield _setup_hosts


@pytest.fixture
def setup_date_time_hosts_for_string_filtering(host_inventory: ApplicationHostInventory):
    def _setup_hosts(field: Field):
        name = field.name
        hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(4)
        value1 = generate_timestamp(delta=datetime.timedelta(days=1))
        value2 = generate_timestamp(delta=datetime.timedelta(days=3))
        value3 = generate_timestamp(delta=datetime.timedelta(days=5))
        hosts_data[0]["system_profile"][name] = value1
        hosts_data[1]["system_profile"][name] = value2
        hosts_data[2]["system_profile"][name] = value3
        hosts_data[3]["system_profile"].pop(name, None)
        return host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    yield _setup_hosts


@pytest.fixture
def setup_enum_hosts_for_string_filtering(host_inventory: ApplicationHostInventory):
    def _setup_hosts(field: Field):
        name = field.name
        assert field.correct_values is not None
        hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
        hosts_data[0]["system_profile"][name] = field.correct_values[0]
        if len(field.correct_values) > 1:
            hosts_data[1]["system_profile"][name] = field.correct_values[1]
        else:
            hosts_data[1]["system_profile"][name] = field.correct_values[0]
        hosts_data[2]["system_profile"].pop(name, None)
        return host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    yield _setup_hosts


@pytest.fixture
def setup_hosts_for_integer_filtering(host_inventory: ApplicationHostInventory):
    def _setup_hosts(field: Field):
        name = field.name
        assert isinstance(field.min, int)
        assert isinstance(field.max, int)
        hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(4)
        value1 = randint(field.min, field.max - 2)
        value2 = randint(value1 + 1, field.max - 1)
        value3 = randint(value2 + 1, field.max)
        hosts_data[0]["system_profile"][name] = value1
        hosts_data[1]["system_profile"][name] = value2
        hosts_data[2]["system_profile"][name] = value3
        hosts_data[3]["system_profile"].pop(name, None)
        return host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    yield _setup_hosts


@pytest.fixture
def setup_hosts_for_boolean_filtering(host_inventory: ApplicationHostInventory):
    def _setup_hosts(field: Field):
        name = field.name
        hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
        hosts_data[0]["system_profile"][name] = True
        hosts_data[1]["system_profile"][name] = False
        hosts_data[2]["system_profile"].pop(name, None)
        return host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    yield _setup_hosts


@pytest.fixture
def setup_hosts_for_filtering(
    setup_string_hosts_for_string_filtering,
    setup_uuid_hosts_for_string_filtering,
    setup_date_time_hosts_for_string_filtering,
    setup_enum_hosts_for_string_filtering,
    setup_hosts_for_integer_filtering,
    setup_hosts_for_boolean_filtering,
):
    HOST_SETUP_BY_TYPE = {
        "str": setup_string_hosts_for_string_filtering,
        "canonical_uuid": setup_uuid_hosts_for_string_filtering,
        "date-time": setup_date_time_hosts_for_string_filtering,
        "enum": setup_enum_hosts_for_string_filtering,
        "int": setup_hosts_for_integer_filtering,
        "int64": setup_hosts_for_integer_filtering,
        "bool": setup_hosts_for_boolean_filtering,
    }

    def _setup_hosts(field):
        return HOST_SETUP_BY_TYPE[field.type](field)

    yield _setup_hosts


@pytest.fixture(scope="module")
def setup_hosts_for_operating_system_filtering(
    host_inventory: ApplicationHostInventory, host_inventory_secondary: ApplicationHostInventory
) -> tuple[list[HostOut], list[list[StructuredTag]]]:
    # Let's have 3 hosts per OS name per account + 1 host without OS per account: 14 hosts together
    os_versions = [(7, 5), (7, 10), (8, 0)]
    os_list = [generate_operating_system("RHEL", major, minor) for major, minor in os_versions]
    os_list += [
        generate_operating_system("CentOS Linux", major, minor) for major, minor in os_versions
    ]

    # Creating a host without OS is impossible via archive upload in a 'legit' way.
    # To achieve this, we have to generate an invalid OS which puptoo isn't able to process.
    os_list.append(generate_operating_system("Fake OS", 99, 99))

    # Create hosts in the primary account
    hosts_data = []
    sorted_tags = []
    for operating_system in os_list:
        archive, core_collect = get_archive_and_collect_method(operating_system["name"])
        hosts_data.append(
            HostData(
                operating_system=operating_system, base_archive=archive, core_collect=core_collect
            )
        )
    primary_hosts = host_inventory.upload.create_hosts(
        hosts_data=hosts_data, cleanup_scope="module"
    )
    tags = host_inventory.apis.hosts.get_host_tags(primary_hosts)
    sorted_tags.extend(tags[host.id] for host in primary_hosts)

    # Create hosts in the secondary account
    hosts_data = []
    for operating_system in os_list:
        archive, core_collect = get_archive_and_collect_method(operating_system["name"])
        hosts_data.append(
            HostData(
                operating_system=operating_system, base_archive=archive, core_collect=core_collect
            )
        )
    secondary_hosts = host_inventory_secondary.upload.create_hosts(
        hosts_data=hosts_data, cleanup_scope="module"
    )
    tags = host_inventory_secondary.apis.hosts.get_host_tags(secondary_hosts)
    sorted_tags.extend(tags[host.id] for host in secondary_hosts)

    return primary_hosts + secondary_hosts, sorted_tags


@pytest.fixture(scope="module")
def setup_hosts_for_os_rhc_filtering(
    host_inventory: ApplicationHostInventory, host_inventory_secondary: ApplicationHostInventory
) -> list[HostWrapper]:
    hosts_data_primary = host_inventory.datagen.create_n_hosts_data_with_tags(6)
    hosts_data_secondary = host_inventory_secondary.datagen.create_n_hosts_data_with_tags(6)

    for hosts_data in (hosts_data_primary, hosts_data_secondary):
        for i in range(3):
            hosts_data[i]["system_profile"].pop("rhc_client_id", None)
        for i in range(3, 6):
            hosts_data[i]["system_profile"]["rhc_client_id"] = generate_uuid()

        for i in range(2):
            hosts_data[i * 3]["system_profile"]["operating_system"] = {
                "major": "8",
                "minor": "6",
                "name": "RHEL",
            }
            hosts_data[i * 3 + 1]["system_profile"]["operating_system"] = {
                "major": "7",
                "minor": "10",
                "name": "RHEL",
            }
            hosts_data[i * 3 + 2]["system_profile"].pop("operating_system", None)

    # Create hosts in the primary account
    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data_primary, cleanup_scope="module"
    )

    # Create hosts in the secondary account
    hosts_secondary = host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data_secondary,
        cleanup_scope="module",
    )

    return hosts + hosts_secondary


@pytest.fixture(scope="module")
def setup_hosts_for_os_display_name_filtering(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
) -> tuple[list[HostOut], list[list[StructuredTag]]]:
    # Let's have 3 hosts per account: 6 hosts together
    os_versions = [(7, 5), (7, 10), (8, 0)]
    os_list = [generate_operating_system("RHEL", major, minor) for major, minor in os_versions]

    # Create hosts in the primary account
    hosts = []
    tags = []
    for i, operating_system in enumerate(os_list):
        host = host_inventory.upload.create_host(
            operating_system=operating_system,
            display_name=f"{FILTER_OS_DISPLAY_NAME}-{i}",
            cleanup_scope="module",
        )
        host_tags = host_inventory.apis.hosts.get_host_tags_response(host).results[host.id]
        hosts.append(host)
        tags.append(host_tags)

    # Create hosts in the secondary account
    for i, operating_system in enumerate(os_list):
        host = host_inventory_secondary.upload.create_host(
            operating_system=operating_system,
            display_name=f"{FILTER_OS_DISPLAY_NAME}-{i}",
            cleanup_scope="module",
        )
        host_tags = host_inventory_secondary.apis.hosts.get_host_tags_response(host).results[
            host.id
        ]
        hosts.append(host)
        tags.append(host_tags)

    return hosts, tags


@pytest.fixture
def mq_setup_hosts_data_for_reporter_filtering(
    host_inventory: ApplicationHostInventory,
) -> list[HostWrapper]:
    hosts_data = host_inventory.datagen.create_hosts_data_for_reporter_filtering("reporter_test")
    return host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.fixture
def mq_setup_hosts_for_sap_sids_filtering(
    host_inventory: ApplicationHostInventory,
    hbi_kafka_setup_hosts_for_sap_sids_endpoint,
):
    host_data = host_inventory.datagen.create_host_data_for_sap_filtering()
    return [
        *hbi_kafka_setup_hosts_for_sap_sids_endpoint,
        host_inventory.kafka.create_host(host_data),
    ]


@pytest.fixture
def mq_setup_hosts_for_sap_system_filtering(
    host_inventory: ApplicationHostInventory,
    openapi_client: HostsApi,
    openapi_client_tags: TagsApi,
):
    # Cleanup
    delete_hosts_by_tags(SAP_FILTER_TAG, openapi_client, openapi_client_tags)

    hosts_data = [host_inventory.datagen.create_host_data_for_sap_filtering() for _ in range(3)]
    hosts_data[0]["system_profile"]["sap_system"] = False
    hosts_data[0]["system_profile"]["workloads"] = {"sap": {"sap_system": False}}
    hosts_data[1]["system_profile"]["sap_system"] = True
    hosts_data[1]["system_profile"]["workloads"] = {"sap": {"sap_system": True}}

    return host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.fixture
def setup_hosts_for_ansible_filtering(host_inventory: ApplicationHostInventory):
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(4)

    for i in range(4):
        if "workloads" not in hosts_data[i]["system_profile"]:
            hosts_data[i]["system_profile"]["workloads"] = {"ansible": {}}

    hosts_data[0]["system_profile"]["workloads"]["ansible"] = {
        "controller_version": "1.2.3",
        "hub_version": "4.5.6",
        "catalog_worker_version": "7.8.9",
        "sso_version": "10.11.12",
    }
    hosts_data[1]["system_profile"]["workloads"]["ansible"] = {
        "controller_version": "4.5.6",
        "hub_version": "7.8.9",
        "catalog_worker_version": "10.11.12",
        "sso_version": "1.2.3",
    }
    hosts_data[2]["system_profile"]["workloads"]["ansible"] = {
        "controller_version": "1.2.3",
        "hub_version": "7.8.9",
    }
    hosts_data[3]["system_profile"]["workloads"].pop("ansible", None)
    return host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.fixture
def setup_hosts_for_sap_filtering(host_inventory: ApplicationHostInventory):
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(7)

    for i in range(7):
        if "workloads" not in hosts_data[i]["system_profile"]:
            hosts_data[i]["system_profile"]["workloads"] = {"sap": {}}

    hosts_data[0]["system_profile"]["workloads"]["sap"] = {
        "sap_system": True,
        "sids": ["H20"],
        "instance_number": "01",
        "version": "1.00.122.04.1478575636",
    }
    hosts_data[1]["system_profile"]["workloads"]["sap"] = {
        "sap_system": True,
        "sids": ["H20", "H30"],
        "version": "2.00.122.04.1478575636",
    }
    hosts_data[2]["system_profile"]["workloads"]["sap"] = {
        "sap_system": True,
        "sids": ["H30"],
        "instance_number": "02",
        "version": "1.00.122.04.1478575636",
    }
    hosts_data[3]["system_profile"]["workloads"]["sap"] = {
        "sap_system": False,
        "sids": ["H20", "H30", "H40"],
    }
    hosts_data[4]["system_profile"]["workloads"]["sap"] = {
        "sap_system": False,
        "sids": ["H20", "H30"],
    }
    hosts_data[5]["system_profile"]["workloads"]["sap"] = {
        "sap_system": False,
        "instance_number": "03",
    }
    hosts_data[6]["system_profile"]["workloads"].pop("sap", None)
    return host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.fixture
def setup_hosts_for_mssql_filtering(host_inventory: ApplicationHostInventory):
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)

    for i in range(3):
        if "workloads" not in hosts_data[i]["system_profile"]:
            hosts_data[i]["system_profile"]["workloads"] = {"mssql": {}}

    hosts_data[0]["system_profile"]["workloads"]["mssql"] = {"version": "15.2.0"}
    hosts_data[1]["system_profile"]["workloads"]["mssql"] = {"version": "1.2.3"}
    hosts_data[2]["system_profile"]["workloads"].pop("mssql", None)
    return host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.fixture(scope="module")
def setup_hosts_for_bootc_status_filtering(
    host_inventory: ApplicationHostInventory,
) -> list[HostWrapper]:
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(10)
    hosts_data[0]["system_profile"].pop("bootc_status", None)

    hosts_data[1]["system_profile"]["bootc_status"] = {
        "booted": {
            "image": "quay.io/b-1:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000a1",  # noqa: E501
            "cached_image": "quay.io/bc-1:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000ac1",  # noqa: E501
        }
    }
    hosts_data[2]["system_profile"]["bootc_status"] = {
        "rollback": {
            "image": "quay.io/r-2:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000b2",  # noqa: E501
            "cached_image": "quay.io/rc-2:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000bc2",  # noqa: E501
        }
    }
    hosts_data[3]["system_profile"]["bootc_status"] = {
        "staged": {
            "image": "quay.io/s-3:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000c3",  # noqa: E501
            "cached_image": "quay.io/sc-3:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000cc3",  # noqa: E501
        }
    }

    hosts_data[4]["system_profile"]["bootc_status"] = {
        "booted": {
            "image": "quay.io/b-4:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000a4",  # noqa: E501
            "cached_image": "quay.io/bc-4:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000ac4",  # noqa: E501
        },
        "staged": {
            "image": "quay.io/s-4:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000c4",  # noqa: E501
            "cached_image": "quay.io/sc-4:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000cc4",  # noqa: E501
        },
    }

    hosts_data[5]["system_profile"]["bootc_status"] = {
        "booted": {
            "image": "quay.io/b-5:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000a5",  # noqa: E501
        }
    }
    hosts_data[6]["system_profile"]["bootc_status"] = {
        "booted": {
            "cached_image": "quay.io/bc-6:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000ac6",  # noqa: E501
        }
    }

    hosts_data[7]["system_profile"]["bootc_status"] = {
        "booted": {
            "image": "quay.io/b-7:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000a7",  # noqa: E501
            "cached_image": "quay.io/bc-7:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000ac7",  # noqa: E501
        },
        "rollback": {
            "image": "quay.io/r-7:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000b7",  # noqa: E501
            "cached_image": "quay.io/rc-7:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000bc7",  # noqa: E501
        },
        "staged": {
            "image": "quay.io/s-7:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000c7",  # noqa: E501
            "cached_image": "quay.io/sc-7:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000cc7",  # noqa: E501
        },
    }
    hosts_data[8]["system_profile"]["bootc_status"] = {
        "booted": {
            "image": "quay.io/b-8:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000a8",  # noqa: E501
            "cached_image": "quay.io/bc-8:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000ac8",  # noqa: E501
        },
        "rollback": {
            "image": "quay.io/r-8:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000b8",  # noqa: E501
            "cached_image": "quay.io/rc-8:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000bc8",  # noqa: E501
        },
        "staged": {
            "image": "quay.io/s-8:latest",
            "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000c8",  # noqa: E501
            "cached_image": "quay.io/sc-8:latest",
            "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000cc8",  # noqa: E501
        },
    }

    hosts_data[9]["system_profile"].pop("bootc_status", None)
    hosts_data[9]["system_profile"]["host_type"] = "edge"

    return host_inventory.kafka.create_hosts(hosts_data=hosts_data, cleanup_scope="module")


def _prepare_hosts_for_registered_with_filter(
    host_inventory: ApplicationHostInventory, scope: str
) -> dict[str, HostWrapper]:
    hosts = {}

    # hosts with 1 reporter
    for reporter in _CORRECT_REGISTERED_WITH_VALUES:
        host_data = host_inventory.datagen.create_host_data_with_tags(reporter=reporter)
        hosts[reporter] = host_inventory.kafka.create_host(
            host_data=host_data, cleanup_scope=scope, wait_for_created=False
        )

    # host with all valid reporters
    host_data_all_reporters = host_inventory.datagen.create_host_data_with_tags()
    hosts["all"] = host_inventory.kafka.create_host(
        host_data=host_data_all_reporters, cleanup_scope=scope, wait_for_created=False
    )
    for reporter in _CORRECT_REGISTERED_WITH_VALUES:
        host_data_all_reporters["reporter"] = reporter
        hosts["all"] = host_inventory.kafka.create_host(
            host_data=host_data_all_reporters, cleanup_scope=scope, wait_for_created=False
        )

    # host with no valid reporters
    no_reporter_host_data = host_inventory.datagen.create_host_data_with_tags(
        reporter=generate_uuid()
    )
    hosts["invalid"] = host_inventory.kafka.create_host(
        host_data=no_reporter_host_data, cleanup_scope=scope, wait_for_created=False
    )

    host_inventory.apis.hosts.wait_for_created(list(hosts.values()))

    return hosts


@pytest.fixture(scope="class")
def prepare_hosts_for_registered_with_filter_class(
    host_inventory: ApplicationHostInventory,
) -> dict[str, HostWrapper]:
    return _prepare_hosts_for_registered_with_filter(host_inventory, "class")


@pytest.fixture(scope="function")
def prepare_hosts_for_registered_with_filter_function(
    host_inventory: ApplicationHostInventory,
) -> dict[str, HostWrapper]:
    return _prepare_hosts_for_registered_with_filter(host_inventory, "function")


@pytest.fixture(scope="module")
def prepare_hosts_for_incorrect_filter_comparator(
    host_inventory: ApplicationHostInventory,
) -> list[HostWrapper]:
    """We just want a few hosts which have all the fields populated"""
    hosts_data = host_inventory.datagen.create_n_complete_hosts_data(
        3, is_sap_system=True, is_edge=True, is_image_mode=True
    )
    return host_inventory.kafka.create_hosts(hosts_data=hosts_data, cleanup_scope="module")


@pytest.fixture(scope="module")
def setup_hosts_for_rhel_ai_filtering(
    host_inventory: ApplicationHostInventory,
) -> list[HostWrapper]:
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(7)
    hosts_data[0]["system_profile"].pop("rhel_ai", None)
    hosts_data[0]["system_profile"].pop("workloads", None)

    # Use workloads.rhel_ai with the new gpu_models structure
    hosts_data[1]["system_profile"]["workloads"] = {
        "rhel_ai": {
            "variant": "RHEL AI",
            "rhel_ai_version_id": "v1.1.3",
            "gpu_models": [
                {"name": "NVIDIA T1000", "vendor": "Nvidia"},
                {"name": "Tesla V100-PCIE-16GB", "vendor": "Nvidia"},
                {"name": "Habana Labs Ltd. Device", "vendor": "Intel"},
                {"name": "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34", "vendor": "AMD"},
            ],
        }
    }
    hosts_data[2]["system_profile"]["workloads"] = {
        "rhel_ai": {
            "variant": "RHEL AI",
            "rhel_ai_version_id": "v1.1.2",
            "gpu_models": [
                {"name": "Habana Labs Ltd. Device 10202", "vendor": "Intel"},
                {"name": "Habana Labs Ltd. HL-2000 AI Training Accelerator", "vendor": "Intel"},
                {"name": "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c31", "vendor": "AMD"},
                {"name": "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34", "vendor": "AMD"},
            ],
        }
    }
    hosts_data[3]["system_profile"]["workloads"] = {
        "rhel_ai": {
            "variant": "RHEL AI",
            "rhel_ai_version_id": "v1.1.3",
            "gpu_models": [
                {"name": "NVIDIA T1000", "vendor": "Nvidia"},
                {"name": "Tesla V100-PCIE-16GB", "vendor": "Nvidia"},
                {"name": "Tesla 2", "vendor": "Nvidia"},
                {"name": "Habana Labs Ltd. Device 10202", "vendor": "Intel"},
                {"name": "Habana Labs Ltd. HL-2001 AI Training Accelerator", "vendor": "Intel"},
                {"name": "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c34", "vendor": "AMD"},
                {
                    "name": "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c350000",
                    "vendor": "AMD",
                },
            ],
        }
    }

    hosts_data[4]["system_profile"]["workloads"] = {
        "rhel_ai": {
            "variant": "RHEL AI",
            "rhel_ai_version_id": "v1.1.4",
            "gpu_models": [
                {"name": "Tesla V100-PCIE-16GB", "vendor": "Nvidia"},
                {"name": "Habana Labs Ltd. Device 1020", "vendor": "Intel"},
                {"name": "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c32", "vendor": "AMD"},
            ],
        }
    }
    hosts_data[5]["system_profile"]["workloads"] = {
        "rhel_ai": {
            "variant": "RHEL AI",
            "rhel_ai_version_id": "v1.1.4",
            "gpu_models": [
                {"name": "NVIDIA T1000", "vendor": "Nvidia"},
                {"name": "Advanced Micro Devices, Inc. [AMD/ATI] Device 0c31", "vendor": "AMD"},
            ],
        }
    }
    hosts_data[6]["system_profile"]["workloads"] = {
        "rhel_ai": {
            "rhel_ai_version_id": "v1.1.4",
            "gpu_models": [
                {"name": "NVIDIA T1000", "vendor": "Nvidia"},
                {"name": "Habana Labs Ltd. Device 1021", "vendor": "Intel"},
            ],
        }
    }

    return host_inventory.kafka.create_hosts(hosts_data=hosts_data, cleanup_scope="module")


@pytest.fixture(scope="module")
def setup_hosts_for_system_type_filtering(
    host_inventory: ApplicationHostInventory,
) -> dict[str, list[HostWrapper]]:
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(10)

    bootc_data = hosts_data[:4]
    for host in bootc_data:
        host["system_profile"]["bootc_status"] = {
            "booted": {
                "image": "quay.io/b-1:latest",
                "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000a1",  # noqa: E501
                "cached_image": "quay.io/bc-1:latest",
                "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000ac1",  # noqa: E501
            }
        }
    conventional_data = hosts_data[4:]
    for host in conventional_data:
        host["system_profile"].pop("bootc_status", None)

    edge_data = host_inventory.datagen.create_n_hosts_data_with_tags(3, host_type="edge")
    for host in edge_data:
        host["system_profile"].pop("bootc_status", None)

    bootc = host_inventory.kafka.create_hosts(hosts_data=bootc_data, cleanup_scope="module")
    conventional = host_inventory.kafka.create_hosts(
        hosts_data=conventional_data, cleanup_scope="module"
    )
    edge = host_inventory.kafka.create_hosts(hosts_data=edge_data, cleanup_scope="module")

    return {"bootc": bootc, "conventional": conventional, "edge": edge}


@pytest.fixture
def setup_hosts_for_deleting_by_system_type_filter(
    host_inventory: ApplicationHostInventory,
) -> dict[str, list[HostWrapper]]:
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(10)

    bootc_data = hosts_data[:4]
    for host in bootc_data:
        host["system_profile"]["bootc_status"] = {
            "booted": {
                "image": "quay.io/b-1:latest",
                "image_digest": "sha256:abcdefABCDEF01234567890000000000000000000000000000000000000000a1",  # noqa: E501
                "cached_image": "quay.io/bc-1:latest",
                "cached_image_digest": "sha256:abcdefABCDEF0123456789000000000000000000000000000000000000000ac1",  # noqa: E501
            }
        }
    conventional_data = hosts_data[4:]
    for host in conventional_data:
        host["system_profile"].pop("bootc_status", None)

    edge_data = host_inventory.datagen.create_n_hosts_data_with_tags(3, host_type="edge")
    for host in edge_data:
        host["system_profile"].pop("bootc_status", None)

    bootc = host_inventory.kafka.create_hosts(hosts_data=bootc_data)
    conventional = host_inventory.kafka.create_hosts(hosts_data=conventional_data)
    edge = host_inventory.kafka.create_hosts(hosts_data=edge_data)

    return {"bootc": bootc, "conventional": conventional, "edge": edge}
