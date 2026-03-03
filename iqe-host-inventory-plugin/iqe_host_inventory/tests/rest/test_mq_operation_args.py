"""
metadata:
  requirements: inv-mq-operation-args
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime

import pytest
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.utils import normalize_datetime_to_utc
from iqe_host_inventory.utils.datagen_utils import SYSTEM_PROFILE
from iqe_host_inventory.utils.datagen_utils import generate_complete_system_profile
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name
from iqe_host_inventory.utils.staleness_utils import create_hosts_in_state

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


def _normalize_datetime_fields(data: dict) -> None:
    """Convert timestamp strings to datetime and normalize to UTC (in-place)."""
    for key, value in data.items():
        try:
            if isinstance(value, str):
                value = datetime.fromisoformat(value)
            if isinstance(value, datetime):
                data[key] = normalize_datetime_to_utc(value)
        except (TypeError, ValueError):
            pass


def _normalize_workloads(data: dict) -> None:
    """Add missing workload types as None (in-place)."""
    if "workloads" not in data or not isinstance(data["workloads"], dict):
        return
    workloads_field = get_sp_field_by_name("workloads")
    if workloads_field.example is None:
        return
    for workload_name in workloads_field.example.keys():
        if workload_name not in data["workloads"]:
            data["workloads"][workload_name] = None


def normalize_system_profile(system_profile: dict) -> dict:
    normalized = deepcopy(system_profile)

    _normalize_datetime_fields(normalized)

    # Add missing fields as None for consistent comparison.
    # The API uses jsonb_strip_nulls so the server response omits null values,
    # but the OpenAPI client's to_dict() adds all schema fields with None defaults.
    # This normalization ensures both the API response and expected test data have
    # the same keys, allowing proper dict equality comparison.
    for field in SYSTEM_PROFILE:
        if field.name not in normalized:
            normalized[field.name] = None

    _normalize_workloads(normalized)

    # Remove top-level rhel_ai - it's not backward compatible because the legacy structure
    # (nvidia_gpu_models, amd_gpu_models, intel_gaudi_hpu_models as separate string arrays)
    # differs from workloads.rhel_ai (unified gpu_models array of objects).
    # Data sent as top-level rhel_ai is migrated to workloads.rhel_ai but NOT extracted back.
    normalized.pop("rhel_ai", None)

    return normalized


@pytest.mark.ephemeral
def test_mq_operation_args_empty_dict(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4462

    metadata:
      assignee: fstavela
      importance: medium
      title: MQ operation_args: empty dict
    """
    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["reporter"] = "puptoo"
    host_data1["system_profile"] = generate_complete_system_profile()
    host_data1["ansible_host"] = generate_display_name()
    host = host_inventory.kafka.create_host(host_data=host_data1)

    host_data2 = deepcopy(host_data1)
    host_data2["reporter"] = "rhsm-system-profile-bridge"
    host_data2["system_profile"] = generate_complete_system_profile()
    host_data2["ansible_host"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(host_data=host_data2, operation_args={})

    assert updated_host.id == host.id
    assert updated_host.reporter == "rhsm-system-profile-bridge"
    assert updated_host.ansible_host == host_data2["ansible_host"]
    assert updated_host.system_profile == host_data2["system_profile"]

    response_host = host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=host_data2["ansible_host"]
    )[0]
    assert response_host.id == host.id
    assert response_host.reporter == "rhsm-system-profile-bridge"
    assert response_host.ansible_host == host_data2["ansible_host"]

    response_sp = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    actual_sp = normalize_system_profile(response_sp.system_profile.to_dict())
    assert actual_sp == normalize_system_profile(host_data2["system_profile"])


@pytest.mark.ephemeral
def test_mq_operation_args_not_provided(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4462

    metadata:
      assignee: fstavela
      importance: high
      title: MQ operation_args: not provided
    """
    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["reporter"] = "puptoo"
    host_data1["system_profile"] = generate_complete_system_profile()
    host_data1["ansible_host"] = generate_display_name()
    host = host_inventory.kafka.create_host(host_data=host_data1)

    host_data2 = deepcopy(host_data1)
    host_data2["reporter"] = "rhsm-system-profile-bridge"
    host_data2["system_profile"] = generate_complete_system_profile()
    host_data2["ansible_host"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(
        host_data=host_data2,
        operation_args=None,
    )

    assert updated_host.id == host.id
    assert updated_host.reporter == "rhsm-system-profile-bridge"
    assert updated_host.ansible_host == host_data2["ansible_host"]
    assert updated_host.system_profile == host_data2["system_profile"]

    response_host = host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=host_data2["ansible_host"]
    )[0]
    assert response_host.id == host.id
    assert response_host.reporter == "rhsm-system-profile-bridge"
    assert response_host.ansible_host == host_data2["ansible_host"]

    response_sp = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    actual_sp = normalize_system_profile(response_sp.system_profile.to_dict())
    assert actual_sp == normalize_system_profile(host_data2["system_profile"])


@pytest.mark.ephemeral
def test_mq_operation_args_random_string(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4462

    metadata:
      assignee: fstavela
      importance: low
      title: MQ operation_args: random arguments
    """

    def _gen_operation_args() -> dict[str, str]:
        return {generate_string_of_length(10): generate_string_of_length(10) for _ in range(3)}

    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["reporter"] = "puptoo"
    host_data1["system_profile"] = generate_complete_system_profile()
    host_data1["ansible_host"] = generate_display_name()
    host = host_inventory.kafka.create_host(
        host_data=host_data1,
        operation_args=_gen_operation_args(),
    )

    host_data2 = deepcopy(host_data1)
    host_data2["reporter"] = "rhsm-system-profile-bridge"
    host_data2["system_profile"] = generate_complete_system_profile()
    host_data2["ansible_host"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(
        host_data=host_data2, operation_args=_gen_operation_args()
    )

    assert updated_host.id == host.id
    assert updated_host.reporter == "rhsm-system-profile-bridge"
    assert updated_host.ansible_host == host_data2["ansible_host"]
    assert updated_host.system_profile == host_data2["system_profile"]

    response_host = host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=host_data2["ansible_host"]
    )[0]
    assert response_host.id == host.id
    assert response_host.reporter == "rhsm-system-profile-bridge"
    assert response_host.ansible_host == host_data2["ansible_host"]

    response_sp = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    actual_sp = normalize_system_profile(response_sp.system_profile.to_dict())
    assert actual_sp == normalize_system_profile(host_data2["system_profile"])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "operation_args",
    [generate_string_of_length(10), [generate_string_of_length(10)], [{}]],
    ids=["string", "list of string", "list of dict"],
)
def test_mq_operation_args_wrong_type(
    host_inventory: ApplicationHostInventory, operation_args: str | list[str] | list[dict]
):
    """
    https://issues.redhat.com/browse/ESSNTL-4462
    https://issues.redhat.com/browse/ESSNTL-4871

    metadata:
      assignee: fstavela
      importance: low
      title: MQ operation_args: wrong type
    """
    host_data = host_inventory.datagen.create_host_data()
    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.create_host(
            host_data=host_data,
            operation_args=operation_args,  # type: ignore[arg-type]
            timeout=1,
        )
    host_inventory.apis.hosts.verify_not_created(retries=1, insights_id=host_data["insights_id"])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "reporter1, reporter2",
    [("puptoo", "rhsm-system-profile-bridge"), ("rep1", "rep2"), ("puptoo", "puptoo")],
)
def test_mq_operation_args_defer_to_fresh_reporter(
    host_inventory: ApplicationHostInventory, reporter1: str, reporter2: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4462

    metadata:
      requirements: inv-mq-defer-to-reporter
      assignee: fstavela
      importance: high
      title: MQ operation_args: defer_to_reporter - fresh reporter
    """
    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["reporter"] = reporter1
    host_data1["system_profile"] = generate_complete_system_profile()
    host_data1["ansible_host"] = generate_display_name()
    host = host_inventory.kafka.create_host(host_data=host_data1)

    host_data2 = deepcopy(host_data1)
    host_data2["reporter"] = reporter2
    host_data2["system_profile"] = generate_complete_system_profile()
    host_data2["ansible_host"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(
        host_data=host_data2, operation_args={"defer_to_reporter": reporter1}
    )

    assert updated_host.id == host.id
    assert updated_host.reporter == reporter2
    assert updated_host.ansible_host == host_data2["ansible_host"]
    assert updated_host.system_profile == host_data1["system_profile"]

    response_host = host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=host_data2["ansible_host"]
    )[0]
    assert response_host.id == host.id
    assert response_host.reporter == reporter2
    assert response_host.ansible_host == host_data2["ansible_host"]

    response_sp = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    actual_sp = normalize_system_profile(response_sp.system_profile.to_dict())
    assert actual_sp == normalize_system_profile(host_data1["system_profile"])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "reporter",
    ["rhsm-system-profile-bridge", "reporter2"],
)
def test_mq_operation_args_defer_to_previous_reporter(
    host_inventory: ApplicationHostInventory, reporter: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4462

    Reporter workflow: puptoo -> rhsm/rep2 -> rhsm (defer to puptoo)

    metadata:
      requirements: inv-mq-defer-to-reporter
      assignee: fstavela
      importance: high
      title: MQ operation_args: defer_to_reporter - previous fresh reporter
    """
    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["reporter"] = "puptoo"
    host_data1["system_profile"] = generate_complete_system_profile()
    host_data1["ansible_host"] = generate_display_name()
    host = host_inventory.kafka.create_host(host_data=host_data1)

    host_data2 = deepcopy(host_data1)
    host_data2["reporter"] = reporter
    host_inventory.kafka.create_host(host_data=host_data2)
    host_inventory.apis.hosts.wait_for_updated(host, reporter=reporter)

    host_data3 = deepcopy(host_data1)
    host_data3["reporter"] = "rhsm-system-profile-bridge"
    host_data3["system_profile"] = generate_complete_system_profile()
    host_data3["ansible_host"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(
        host_data=host_data3, operation_args={"defer_to_reporter": "puptoo"}
    )

    assert updated_host.id == host.id
    assert updated_host.reporter == "rhsm-system-profile-bridge"
    assert updated_host.ansible_host == host_data3["ansible_host"]
    assert updated_host.system_profile == host_data1["system_profile"]

    response_host = host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=host_data3["ansible_host"]
    )[0]
    assert response_host.id == host.id
    assert response_host.reporter == "rhsm-system-profile-bridge"
    assert response_host.ansible_host == host_data3["ansible_host"]

    response_sp = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    actual_sp = normalize_system_profile(response_sp.system_profile.to_dict())
    assert actual_sp == normalize_system_profile(host_data1["system_profile"])


@iqe_blocker(iqe_blocker.jira("RHINENG-15628", category=iqe_blocker.PRODUCT_ISSUE))
@pytest.mark.ephemeral
@pytest.mark.parametrize("fresh_host", [True, False], ids=["fresh host", "stale host"])
@pytest.mark.parametrize(
    "staleness",
    ["stale", "stale_warning"],
    ids=["stale", "stale_warning"],
)
def test_mq_operation_args_defer_to_stale_reporter(
    host_inventory: ApplicationHostInventory, fresh_host: bool, staleness: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4462

    metadata:
      requirements: inv-mq-defer-to-reporter
      assignee: fstavela
      importance: high
      title: MQ operation_args: defer_to_reporter - stale reporter
    """
    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["reporter"] = "puptoo"
    host_data1["system_profile"] = generate_complete_system_profile()
    host_data1["ansible_host"] = generate_display_name()

    deltas = (5, 3600, 3601) if staleness == "stale" else (5, 6, 3600)

    host = create_hosts_in_state(
        host_inventory,
        [host_data1],
        host_state=staleness,
        deltas=deltas,
    )[0]

    puptoo_staleness_timestamp = host.per_reporter_staleness["puptoo"][staleness + "_timestamp"]  # type: ignore

    if fresh_host:
        host_data1["reporter"] = "iqe-host-inventory"
        host = host_inventory.kafka.create_host(host_data1)
        host_inventory.apis.hosts.wait_for_updated(host, reporter=host_data1["reporter"])

    host_data2 = deepcopy(host_data1)
    host_data2["reporter"] = "rhsm-system-profile-bridge"
    host_data2["system_profile"] = generate_complete_system_profile()
    host_data2["ansible_host"] = generate_display_name()

    updated_host = host_inventory.kafka.create_host(
        host_data2, operation_args={"defer_to_reporter": "puptoo"}
    )
    host_inventory.apis.hosts.wait_for_updated(host, reporter=host_data2["reporter"])

    assert updated_host.updated.isoformat() > puptoo_staleness_timestamp
    assert updated_host.id == host.id
    assert updated_host.reporter == "rhsm-system-profile-bridge"
    assert updated_host.ansible_host == host_data2["ansible_host"]
    assert updated_host.system_profile == host_data2["system_profile"]

    response_host = host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=host_data2["ansible_host"]
    )[0]
    assert response_host.id == host.id
    assert response_host.reporter == "rhsm-system-profile-bridge"
    assert response_host.ansible_host == host_data2["ansible_host"]

    response_sp = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    actual_sp = normalize_system_profile(response_sp.system_profile.to_dict())
    assert actual_sp == normalize_system_profile(host_data2["system_profile"])


@pytest.mark.ephemeral
def test_mq_operation_args_defer_to_not_existing_reporter(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4462

    metadata:
      requirements: inv-mq-defer-to-reporter
      assignee: fstavela
      importance: high
      title: MQ operation_args: defer_to_reporter - not existing reporter
    """
    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["reporter"] = "reporter1"
    host_data1["system_profile"] = generate_complete_system_profile()
    host_data1["ansible_host"] = generate_display_name()
    host = host_inventory.kafka.create_host(host_data1)

    host_data2 = deepcopy(host_data1)
    host_data2["reporter"] = "rhsm-system-profile-bridge"
    host_data2["system_profile"] = generate_complete_system_profile()
    host_data2["ansible_host"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(
        host_data2,
        operation_args={"defer_to_reporter": "puptoo"},
    )

    assert updated_host.id == host.id
    assert updated_host.reporter == "rhsm-system-profile-bridge"
    assert updated_host.ansible_host == host_data2["ansible_host"]
    assert updated_host.system_profile == host_data2["system_profile"]

    response_host = host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=host_data2["ansible_host"]
    )[0]
    assert response_host.id == host.id
    assert response_host.reporter == "rhsm-system-profile-bridge"
    assert response_host.ansible_host == host_data2["ansible_host"]

    response_sp = host_inventory.apis.hosts.get_host_system_profile(updated_host)
    actual_sp = normalize_system_profile(response_sp.system_profile.to_dict())
    assert actual_sp == normalize_system_profile(host_data2["system_profile"])


@pytest.mark.ephemeral
def test_mq_operation_args_defer_to_reporter_create_host(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4462

    metadata:
      requirements: inv-mq-defer-to-reporter
      assignee: fstavela
      importance: medium
      title: MQ operation_args: defer_to_reporter - while creating new host
    """
    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["reporter"] = "puptoo"
    host_data1["system_profile"] = generate_complete_system_profile()
    host_data1["ansible_host"] = generate_display_name()
    host = host_inventory.kafka.create_host(host_data1)

    host_data2 = host_inventory.datagen.create_host_data()
    host_data2["reporter"] = "rhsm-system-profile-bridge"
    host_data2["system_profile"] = generate_complete_system_profile()
    host_data2["ansible_host"] = generate_display_name()
    host2 = host_inventory.kafka.create_host(
        host_data2, operation_args={"defer_to_reporter": "puptoo"}
    )

    assert host2.id != host.id
    assert host2.reporter == "rhsm-system-profile-bridge"
    assert host2.ansible_host == host_data2["ansible_host"]
    assert host2.system_profile == host_data2["system_profile"]

    response_host = host_inventory.apis.hosts.get_host_system_profile(host2)
    actual_sp = normalize_system_profile(response_host.system_profile.to_dict())
    expected_sp = normalize_system_profile(host_data2["system_profile"])
    assert actual_sp == expected_sp
