# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from collections.abc import Generator
from random import choice
from random import randint

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.deprecations import DEPRECATE_FIND_MQ_HOST_MSGS
from iqe_host_inventory.deprecations import DEPRECATE_MQ_CREATE_OR_UPDATE_HOST
from iqe_host_inventory.fixtures.cleanup_fixtures import HBICleanupRegistry
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.modeling.wrappers import HostMessageWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.kafka_utils import log_consumed_host_message
from iqe_host_inventory.utils.kafka_utils import match_hosts
from iqe_host_inventory.utils.kafka_utils import wrap_payload

logger = logging.getLogger(__name__)


@pytest.fixture
def mq_create_or_update_host(
    produce_msgs: Callable,
    find_mq_host_msgs: Callable,
    host_inventory: ApplicationHostInventory,
    hbi_cleanup_function: HBICleanupRegistry,
) -> Callable:
    warnings.warn(DEPRECATE_MQ_CREATE_OR_UPDATE_HOST, stacklevel=2)

    def _mq_create_or_update_host(
        host_data: dict | None = None,
        extra_data: dict | None = None,
        metadata: dict | None = None,
        operation_args: dict | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        field_to_match: str = "insights_id",
        timeout_in_seconds: int = 10,
        host_inventory_app: ApplicationHostInventory = host_inventory,
        return_events_message: bool = False,
        wait_for_existing: bool = False,
        retain_hosts: bool = False,
    ) -> HostWrapper | HostMessageWrapper:
        extra_data = extra_data or {}
        host_data = host_data or host_inventory_app.datagen.create_host_data(**extra_data)
        host_message = wrap_payload(
            host_data,
            identity=host_inventory_app.kafka.identity,
            metadata=metadata,
            operation_args=operation_args,
            omit_identity=omit_identity,
            omit_metadata=omit_metadata,
            omit_request_id=omit_request_id,
        )

        logger.info(
            f"Creating/Updating a host via MQ to {host_inventory_app.kafka.ingress_topic} topic"
        )
        produce_msgs(host_inventory_app.kafka.ingress_topic, [host_message])
        logger.info(f"Delivered message: {host_message}")

        logger.info("Consuming a host via MQ")
        consumed_host_message = find_mq_host_msgs(
            field_to_match=field_to_match,
            values_to_match=[host_data[field_to_match]],
            timeout_in_seconds=timeout_in_seconds,
        )
        log_consumed_host_message(consumed_host_message, field_to_match)

        host = consumed_host_message.host

        # todo: mq support
        if not retain_hosts:
            hbi_cleanup_function(host_inventory_app)
            host_inventory_app.cleanup.add_hosts(host)
        if wait_for_existing:
            host_inventory_app.apis.hosts.wait_for_created(host)
        if not return_events_message:
            return host

        return consumed_host_message

    return _mq_create_or_update_host


@pytest.fixture
def find_mq_host_msgs(find_msgs: Callable, host_inventory: ApplicationHostInventory) -> Callable:
    warnings.warn(DEPRECATE_FIND_MQ_HOST_MSGS, stacklevel=2)

    def _find_mq_host_msgs(
        field_to_match: str,
        values_to_match: list[object],
        timeout_in_seconds: int = 10,
    ) -> HostMessageWrapper | list[HostMessageWrapper]:
        result = find_msgs(
            topic=host_inventory.kafka.events_topic,
            data_to_match={"field": field_to_match, "values": values_to_match},
            num_matches=len(values_to_match),
            matching_func=match_hosts,
            timeout_in_seconds=timeout_in_seconds,
        )

        if isinstance(result, list):
            if not result:
                raise KafkaMessageNotFoundError(
                    HostMessageWrapper, field_to_match, values_to_match
                )
            return [HostMessageWrapper.from_message(message) for message in result]

        return HostMessageWrapper.from_message(result)

    return _find_mq_host_msgs


@pytest.fixture
def hbi_kafka_setup_hosts_for_sap_sids_endpoint(
    host_inventory: ApplicationHostInventory,
) -> list[HostWrapper]:
    hosts_data = [host_inventory.datagen.create_host_data_for_sap_filtering() for _ in range(2)]

    hosts_data[0]["system_profile"]["sap_sids"] = ["ABC"]
    hosts_data[0]["system_profile"]["sap_system"] = True
    hosts_data[0]["system_profile"]["sap_instance_number"] = "03"
    hosts_data[0]["system_profile"]["sap_version"] = "1.00.122.04.1478575636"

    hosts_data[0]["system_profile"]["workloads"] = {
        "sap": {
            "sids": ["ABC"],
            "sap_system": True,
            "instance_number": "03",
            "version": "1.00.122.04.1478575636",
        }
    }

    hosts_data[1]["system_profile"]["sap_sids"] = ["ABC", "C1E"]
    hosts_data[1]["system_profile"]["sap_system"] = True
    hosts_data[1]["system_profile"]["sap_instance_number"] = "02"
    hosts_data[1]["system_profile"]["sap_version"] = "2.00.122.03.1478575636"

    hosts_data[1]["system_profile"]["workloads"] = {
        "sap": {
            "sids": ["ABC", "C1E"],
            "sap_system": True,
            "instance_number": "02",
            "version": "2.00.122.03.1478575636",
        }
    }

    return host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.fixture(scope="module")
def hbi_kafka_setup_hosts_for_sort_ordering(
    host_inventory: ApplicationHostInventory,
) -> list[HostWrapper]:
    hosts_data = host_inventory.datagen.create_n_hosts_data(10)
    for data in hosts_data:
        data["display_name"] = generate_display_name()
        os_field = {
            "name": choice(["RHEL", "CentOS", "CentOS Linux"]),
            "major": randint(0, 99),
            "minor": randint(0, 99),
        }
        data["system_profile"]["operating_system"] = os_field

    # Same display_name
    hosts_data[3]["display_name"] = hosts_data[0]["display_name"]
    hosts_data[4]["display_name"] = hosts_data[0]["display_name"].upper()

    # Without operating system
    hosts_data[4]["system_profile"].pop("operating_system")
    hosts_data[9]["system_profile"].pop("operating_system")

    # Same OS name, different OS versions
    hosts_data[0]["system_profile"]["operating_system"]["name"] = "RHEL"
    hosts_data[5]["system_profile"]["operating_system"]["name"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["name"]

    # Same OS version, different OS name
    hosts_data[6]["system_profile"]["operating_system"]["name"] = "CentOS Linux"
    hosts_data[6]["system_profile"]["operating_system"]["major"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["major"]
    hosts_data[6]["system_profile"]["operating_system"]["minor"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["minor"]

    # Same OS name and major, different minor
    hosts_data[7]["system_profile"]["operating_system"]["name"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["name"]
    hosts_data[7]["system_profile"]["operating_system"]["major"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]["major"]

    # Same OS
    hosts_data[8]["system_profile"]["operating_system"] = hosts_data[0]["system_profile"][
        "operating_system"
    ]

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data, cleanup_scope="module")

    def _gen_group_name() -> str:
        # Make some group names uppercase
        if choice([True, False]):
            return generate_display_name().upper()
        return generate_display_name()

    # Hosts 0 and 9 are in the same group, Hosts 1 and 8 are without group
    groups_data = [GroupData(name=_gen_group_name(), hosts=[hosts[0], hosts[9]])]
    groups_data += [GroupData(name=_gen_group_name(), hosts=host) for host in hosts[2:8]]
    host_inventory.apis.groups.create_groups(groups_data, cleanup_scope="module")

    return hosts


@pytest.fixture
def hbi_kafka_prepare_host(host_inventory: ApplicationHostInventory) -> Generator[HostWrapper]:
    host = host_inventory.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_kafka_prepare_host_class(
    host_inventory: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_kafka_prepare_host_module(
    host_inventory: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture
def hbi_secondary_kafka_prepare_host(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory_secondary.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_secondary_kafka_prepare_host_class(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory_secondary.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_secondary_kafka_prepare_host_module(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostWrapper]:
    host = host_inventory_secondary.kafka.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)
