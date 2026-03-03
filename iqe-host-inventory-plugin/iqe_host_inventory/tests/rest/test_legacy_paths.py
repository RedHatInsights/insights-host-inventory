# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import os
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from functools import partial

import pytest
from iqe.base.application import Application
from iqe.base.http import RobustSession
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import accept_when
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import get_default_operating_system
from iqe_host_inventory.utils.staleness_utils import extract_staleness_fields
from iqe_host_inventory.utils.staleness_utils import get_staleness_defaults
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)

LEGACY_API_PATH = "/r/insights/platform/inventory/v1"
FACTS_NAMESPACE = "namespace1"
FACTS_FACTS = {"my_fact1": "my_value1"}


def check_legacy_get_hosts(session: RobustSession, base_url: str) -> None:
    url = f"{base_url}/hosts"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"]) >= 1


def check_legacy_get_hosts_by_id(
    session: RobustSession, base_url: str, host: HostOut | HostWrapper
) -> None:
    url = f"{base_url}/hosts/{host.id}"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["id"] == host.id


def check_legacy_get_hosts_system_profile(
    session: RobustSession, base_url: str, host: HostOut | HostWrapper
) -> None:
    url = f"{base_url}/hosts/{host.id}/system_profile"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["id"] == host.id
    assert (
        response.json()["results"][0]["system_profile"]["operating_system"]
        == get_default_operating_system()
    )


def check_legacy_get_hosts_tags(
    session: RobustSession, base_url: str, host: HostOut | HostWrapper
) -> None:
    url = f"{base_url}/hosts/{host.id}/tags"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"].keys()) == 1
    assert len(response.json()["results"][host.id]) > 0


def check_legacy_get_hosts_tags_count(
    session: RobustSession, base_url: str, host: HostOut | HostWrapper
) -> None:
    url = f"{base_url}/hosts/{host.id}/tags/count"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"].keys()) == 1
    assert response.json()["results"][host.id] > 0


def check_legacy_checkin(
    host_inventory: ApplicationHostInventory,
    session: RobustSession,
    base_url: str,
    host: HostOut | HostWrapper,
) -> None:
    post_data = {"insights_id": host.insights_id}
    url = f"{base_url}/hosts/checkin"
    logger.info(f"Legacy URL to be used for the test: POST {url}")
    time = datetime.now(UTC)
    response = session.post(url, json=post_data, verify=False)
    assert response.status_code == 201

    # Get the host and check that the updated timestamp has changed
    host_inventory.apis.hosts.wait_for_updated(
        host.id, updated=time, accuracy=timedelta(milliseconds=500)
    )

    url = f"{base_url}/hosts/{host.id}"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["results"][0]["updated"]) > time


def check_legacy_patch_host(
    host_inventory: ApplicationHostInventory,
    session: RobustSession,
    base_url: str,
    host: HostOut | HostWrapper,
) -> None:
    new_display_name = generate_display_name()
    patch_data = {"display_name": new_display_name}
    url = f"{base_url}/hosts/{host.id}"
    logger.info(f"Legacy URL to be used for the test: PATCH {url}")
    response = session.patch(url, json=patch_data, verify=False)
    assert response.status_code == 200

    # Get the host and check that the patched fields have changed
    host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_display_name)

    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert response.json()["results"][0]["display_name"] == new_display_name


def fetch_facts(
    host_inventory: ApplicationHostInventory, host: HostOut | HostWrapper
) -> dict[str, str]:
    response_host = host_inventory.apis.hosts.get_host_by_id(host.id)
    return response_host.facts[0].facts


def new_facts_found(expected_facts: dict[str, str], facts: dict[str, str]) -> bool:
    return facts == expected_facts


def check_legacy_patch_facts(
    host_inventory: ApplicationHostInventory,
    session: RobustSession,
    base_url: str,
    host: HostOut | HostWrapper,
) -> None:
    patch_data = {"my_fact2": "my_value2"}
    url = f"{base_url}/hosts/{host.id}/facts/{FACTS_NAMESPACE}"
    logger.info(f"Legacy URL to be used for the test: PATCH {url}")
    response = session.patch(url, json=patch_data, verify=False)
    assert response.status_code == 200

    # Get the host and check that the facts have changed
    expected_facts = {**FACTS_FACTS, **patch_data}
    accept_when(
        partial(fetch_facts, host_inventory, host),
        is_valid=partial(new_facts_found, expected_facts),
    )

    url = f"{base_url}/hosts/{host.id}"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"][0]["facts"]) == 1
    assert response.json()["results"][0]["facts"][0]["namespace"] == FACTS_NAMESPACE
    assert response.json()["results"][0]["facts"][0]["facts"] == expected_facts


def check_legacy_put_facts(
    host_inventory: ApplicationHostInventory,
    session: RobustSession,
    base_url: str,
    host: HostOut | HostWrapper,
) -> None:
    put_data = {"my_fact2": "my_value2"}
    url = f"{base_url}/hosts/{host.id}/facts/{FACTS_NAMESPACE}"
    logger.info(f"Legacy URL to be used for the test: PUT {url}")
    response = session.put(url, json=put_data, verify=False)
    assert response.status_code == 200

    # Get the host and check that the facts have changed
    accept_when(
        partial(fetch_facts, host_inventory, host), is_valid=partial(new_facts_found, put_data)
    )

    url = f"{base_url}/hosts/{host.id}"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"][0]["facts"]) == 1
    assert response.json()["results"][0]["facts"][0]["namespace"] == FACTS_NAMESPACE
    assert response.json()["results"][0]["facts"][0]["facts"] == put_data


def check_legacy_delete_hosts_by_id(
    host_inventory: ApplicationHostInventory,
    session: RobustSession,
    base_url: str,
    host: HostOut | HostWrapper,
) -> None:
    url = f"{base_url}/hosts/{host.id}"
    logger.info(f"Legacy URL to be used for the test: DELETE {url}")
    response = session.delete(url, verify=False)
    assert response.status_code == 200

    # Try to get the host and check that the host has been deleted
    host_inventory.apis.hosts.wait_for_deleted(host)

    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 404


def check_legacy_get_groups(session: RobustSession, base_url: str) -> None:
    url = f"{base_url}/groups"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"]) >= 1


def check_legacy_get_resource_types(session: RobustSession, base_url: str) -> None:
    url = f"{base_url}/resource-types"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 1


def check_legacy_get_tags(session: RobustSession, base_url: str) -> None:
    url = f"{base_url}/tags"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"]) >= 1


def check_legacy_get_sp_operating_system(session: RobustSession, base_url: str) -> None:
    url = f"{base_url}/system_profile/operating_system"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    assert len(response.json()["results"]) >= 1


def check_legacy_get_staleness_defaults(session: RobustSession, base_url: str) -> None:
    url = f"{base_url}/account/staleness/defaults"
    logger.info(f"Legacy URL to be used for the test: GET {url}")
    response = session.get(url, verify=False)
    assert response.status_code == 200
    validate_staleness_response(
        extract_staleness_fields(response.json()), get_staleness_defaults()
    )


def check_legacy_endpoints(
    host_inventory: ApplicationHostInventory,
    session: RobustSession,
    base_url: str,
    host: HostOut | HostWrapper,
) -> None:
    """
    Note that some endpoints related to facts PUT/PATCH can't be tested in Stage and Prod since
    we can create those facts only through kafka message, which we can't do outside ephemeral.
    """
    check_legacy_get_hosts(session, base_url)
    check_legacy_get_hosts_by_id(session, base_url, host)
    check_legacy_get_hosts_system_profile(session, base_url, host)
    check_legacy_get_hosts_tags(session, base_url, host)
    check_legacy_get_hosts_tags_count(session, base_url, host)

    check_legacy_get_tags(session, base_url)
    check_legacy_get_sp_operating_system(session, base_url)

    check_legacy_checkin(host_inventory, session, base_url, host)
    check_legacy_patch_host(host_inventory, session, base_url, host)
    check_legacy_delete_hosts_by_id(host_inventory, session, base_url, host)


@pytest.mark.cert_auth
@pytest.mark.skipif(
    not any(env in os.getenv("ENV_FOR_DYNACONF", "stage_proxy") for env in ("stage", "prod")),
    reason="There is a different test for ephemeral",
)
@pytest.mark.parametrize(
    "legacy_hostname, test_app",
    [
        pytest.param(
            lf("hbi_legacy_hostname"),
            lf("application"),
            id="default-auth",
        ),
        pytest.param(
            lf("hbi_legacy_cert_hostname"),
            lf("hbi_application_cert_auth"),
            id="cert-auth",
        ),
    ],
)
def test_legacy_paths(
    host_inventory: ApplicationHostInventory,
    host_inventory_cert_auth: ApplicationHostInventory,
    legacy_hostname: str,
    test_app: Application,
) -> None:
    """
    Test that "legacy paths" are operating correctly in Stage and Prod.

    Note that some endpoints related to facts PUT/PATCH can't be tested in Stage and Prod since
    we can create those facts only through kafka message, which we can't do outside ephemeral.

    https://issues.redhat.com/browse/RHINENG-11455

    metadata:
        requirements: inv-legacy-endpoints
        assignee: fstavela
        importance: high
        title: Inventory: Test that "legacy paths" are operating correctly in Stage and Prod
    """
    session = test_app.http_client
    base_url = f"https://{legacy_hostname}{LEGACY_API_PATH}"

    host = host_inventory_cert_auth.upload.create_host()
    check_legacy_endpoints(host_inventory, session, base_url, host)
    if "cert" not in legacy_hostname:  # These endpoints are forbidden with cert auth (HTTP 403)
        host_inventory.apis.groups.create_n_empty_groups(1)
        check_legacy_get_groups(session, base_url)
        check_legacy_get_resource_types(session, base_url)
        check_legacy_get_staleness_defaults(session, base_url)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "test_host_inventory",
    [
        pytest.param(
            lf("host_inventory_identity_auth_user"),
            id="user",
        ),
        pytest.param(
            lf("host_inventory_identity_auth_system"),
            id="system",
        ),
    ],
)
def test_legacy_paths_ephemeral(
    test_host_inventory: ApplicationHostInventory,
    hbi_ephemeral_base_url: str,
    hbi_default_account_number: str,
) -> None:
    """
    Test that "legacy paths" are operating correctly in ephemeral.

    https://issues.redhat.com/browse/RHINENG-11455

    metadata:
        requirements: inv-legacy-endpoints
        assignee: fstavela
        importance: high
        title: Inventory: Test that "legacy paths" are operating correctly in ephemeral
    """

    host_data = test_host_inventory.datagen.create_host_data_with_tags(
        account_number=hbi_default_account_number
    )
    host_data["facts"] = [{"namespace": FACTS_NAMESPACE, "facts": FACTS_FACTS}]
    sys_conf = test_host_inventory.application.user.get("identity").get("system")
    if sys_conf:  # This is needed for cert auth (system test)
        host_data["system_profile"]["owner_id"] = sys_conf.get("cn")

    host = test_host_inventory.kafka.create_host(host_data=host_data)

    session = test_host_inventory.application.http_client
    base_url = f"{hbi_ephemeral_base_url}{LEGACY_API_PATH}"

    if not sys_conf:  # These endpoints are forbidden with cert auth (HTTP 403)
        test_host_inventory.apis.groups.create_n_empty_groups(1)
        check_legacy_get_groups(session, base_url)
        check_legacy_get_resource_types(session, base_url)
        check_legacy_get_staleness_defaults(session, base_url)

    check_legacy_patch_facts(test_host_inventory, session, base_url, host)
    check_legacy_put_facts(test_host_inventory, session, base_url, host)

    check_legacy_endpoints(test_host_inventory, session, base_url, host)
