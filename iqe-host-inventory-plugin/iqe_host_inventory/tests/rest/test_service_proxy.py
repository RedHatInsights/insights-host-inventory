from __future__ import annotations

import logging
from urllib.parse import urljoin

import pytest
from iqe.base.application import Application

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import accept_when
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_facts
from iqe_host_inventory.utils.datagen_utils import generate_tags
from iqe_host_inventory.utils.tag_utils import sort_tags

pytestmark = [pytest.mark.backend]

SERVICE_PROXY_HOST = "insights-inventory"
SERVICE_PROXY_PORT = "8080"
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def service_proxy_url(application):
    inventory_conf = (
        application.host_inventory.config.get("service_objects").get("api").get("config")
    )
    split_hostname = inventory_conf.get("hostname").split(".")
    split_hostname[0] = SERVICE_PROXY_HOST
    service_proxy_hostname = ".".join(split_hostname)
    base = f"{inventory_conf.get('scheme')}://{service_proxy_hostname}:{SERVICE_PROXY_PORT}"
    url = urljoin(base, inventory_conf.get("path"))
    return url


@pytest.mark.ephemeral
def test_service_proxy_get_all_hosts(application: Application, service_proxy_url: str):
    """
    Test GET on /hosts endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-get-list
        assignee: fstavela
        importance: medium
        title: Test service proxy - GET /hosts
    """
    application.host_inventory.kafka.create_host()

    url = service_proxy_url + "/hosts"
    logger.info(f"REST: {url}")
    response = application.http_client.get(url)
    assert response.status_code == 200
    response = response.json()
    assert response["total"] >= 1
    assert len(response["results"]) >= 1


@pytest.mark.ephemeral
def test_service_proxy_get_host_by_id(application: Application, service_proxy_url: str):
    """
    Test GET on /hosts/<host_id> endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-get-by-id
        assignee: fstavela
        importance: medium
        title: Test service proxy - GET /hosts/<host_id>
    """
    host = application.host_inventory.kafka.create_host()

    url = service_proxy_url + f"/hosts/{host.id}"
    logger.info(f"REST: {url}")
    response = application.http_client.get(url)
    assert response.status_code == 200
    response = response.json()
    assert response["total"] == 1
    assert len(response["results"]) == 1
    assert response["results"][0]["id"] == host.id


@pytest.mark.ephemeral
def test_service_proxy_get_system_profile(
    application: Application,
    service_proxy_url: str,
    host_inventory: ApplicationHostInventory,
):
    """
    Test GET on /hosts/<host_id>/system_profile endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-get-system_profile
        assignee: fstavela
        importance: medium
        title: Test service proxy - GET /hosts/<host_id>/system_profile
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["bios_vendor"] = "test-vendor"
    host = host_inventory.kafka.create_host(host_data)

    url = service_proxy_url + f"/hosts/{host.id}/system_profile"
    logger.info(f"REST: {url}")
    response = application.http_client.get(url)
    assert response.status_code == 200
    response = response.json()
    assert response["total"] == 1
    assert len(response["results"]) == 1
    assert response["results"][0]["id"] == host.id
    assert response["results"][0]["system_profile"]["bios_vendor"] == "test-vendor"


@pytest.mark.ephemeral
def test_service_proxy_get_host_tags(
    application: Application,
    service_proxy_url: str,
    host_inventory: ApplicationHostInventory,
):
    """
    Test GET on /hosts/<host_id>/tags endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-get-tags
        assignee: fstavela
        importance: medium
        title: Test service proxy - GET /hosts/<host_id>/tags
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host = host_inventory.kafka.create_host(host_data)

    url = service_proxy_url + f"/hosts/{host.id}/tags"
    logger.info(f"REST: {url}")
    response = application.http_client.get(url)
    assert response.status_code == 200
    response = response.json()
    assert response["total"] == 1
    assert len(response["results"]) == 1
    assert sort_tags(response["results"][host.id]) == sort_tags(host_data["tags"])


@pytest.mark.ephemeral
def test_service_proxy_get_host_tags_count(
    application: Application,
    service_proxy_url: str,
    host_inventory: ApplicationHostInventory,
):
    """
    Test GET on /hosts/<host_id>/tags/count endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-get-tags-count
        assignee: fstavela
        importance: medium
        title: Test service proxy - GET /hosts/<host_id>/tags/count
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host = host_inventory.kafka.create_host(host_data)

    url = service_proxy_url + f"/hosts/{host.id}/tags/count"
    logger.info(f"REST: {url}")
    response = application.http_client.get(url)
    assert response.status_code == 200
    response = response.json()
    assert response["total"] == 1
    assert len(response["results"]) == 1
    assert response["results"][host.id] == len(host_data["tags"])


@pytest.mark.ephemeral
def test_service_proxy_patch_host(
    host_inventory: ApplicationHostInventory, service_proxy_url: str
):
    """
    Test PATCH on /hosts/<host_id> endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-patch
        assignee: fstavela
        importance: medium
        title: Test service proxy - PATCH /hosts/<host_id>
    """
    host = host_inventory.kafka.create_host()

    url = service_proxy_url + f"/hosts/{host.id}"
    new_display_name = generate_display_name()
    logger.info(f"REST: {url}")
    response = host_inventory.application.http_client.patch(
        url, json={"display_name": new_display_name}
    )
    assert response.status_code == 200

    host_inventory.apis.hosts.wait_for_updated(host, display_name=new_display_name)


@pytest.mark.ephemeral
def test_service_proxy_patch_facts(
    application: Application,
    service_proxy_url: str,
    host_inventory: ApplicationHostInventory,
):
    """
    Test PATCH on /hosts/<host_id>/facts/<namespace> endpoint using the service proxy (port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-patch-facts
        assignee: fstavela
        importance: medium
        title: Test service proxy - PATCH /hosts/<host_id>/facts/<namespace>
    """
    host_data = host_inventory.datagen.create_host_data(facts=generate_facts())
    host = host_inventory.kafka.create_host(host_data)

    url = service_proxy_url + f"/hosts/{host.id}/facts/{host_data['facts'][0]['namespace']}"
    new_facts = generate_facts()[0]["facts"]
    logger.info(f"REST: {url}")
    response = application.http_client.patch(url, json=new_facts)
    assert response.status_code == 200

    def get_host_facts() -> dict[str, object]:
        fresh_host = host_inventory.apis.hosts.get_host_by_id(host)
        return fresh_host.facts[0].to_dict()

    merged_facts = host_data["facts"][0]
    merged_facts["facts"] = {**merged_facts["facts"], **new_facts}

    def host_facts_match_update(facts: dict[str, object]) -> bool:
        return facts == merged_facts

    accept_when(get_host_facts, is_valid=host_facts_match_update)


@pytest.mark.ephemeral
def test_service_proxy_put_facts(
    application: Application,
    service_proxy_url: str,
    host_inventory: ApplicationHostInventory,
):
    """
    Test PUT on /hosts/<host_id>/facts/<namespace> endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-put-facts
        assignee: fstavela
        importance: medium
        title: Test service proxy - PUT /hosts/<host_id>/facts/<namespace>
    """
    host_data = host_inventory.datagen.create_host_data(facts=generate_facts())
    host = host_inventory.kafka.create_host(host_data)

    url = service_proxy_url + f"/hosts/{host.id}/facts/{host_data['facts'][0]['namespace']}"
    new_facts = generate_facts()[0]
    new_facts["namespace"] = host_data["facts"][0]["namespace"]
    logger.info(f"REST: {url}")
    response = application.http_client.put(url, json=new_facts["facts"])
    assert response.status_code == 200

    def get_host_facts() -> list[dict[str, object]]:
        fresh_host = host_inventory.apis.hosts.get_host_by_id(host)
        return [x.to_dict() for x in fresh_host.facts]

    def host_facts_match_update(facts: list[dict[str, object]]) -> bool:
        return facts == [new_facts]

    accept_when(get_host_facts, is_valid=host_facts_match_update)


@pytest.mark.ephemeral
def test_service_proxy_delete_host(
    host_inventory: ApplicationHostInventory, service_proxy_url: str
):
    """
    Test DELETE on /hosts/<host_id> endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-hosts-delete-by-id
        assignee: fstavela
        importance: medium
        title: Test service proxy - DELETE /hosts/<host_id>
    """
    host = host_inventory.kafka.create_host()

    url = service_proxy_url + f"/hosts/{host.id}"
    logger.info(f"REST: {url}")
    response = host_inventory.application.http_client.delete(url)
    assert response.status_code == 200
    host_inventory.apis.hosts.wait_for_deleted(host)


@pytest.mark.ephemeral
def test_service_proxy_get_sap_sids(
    application: Application,
    service_proxy_url: str,
    host_inventory: ApplicationHostInventory,
):
    """
    Test GET on /system_profile/sap_sids endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-system_profile-get-sap_sids
        assignee: fstavela
        importance: medium
        title: Test service proxy - GET /system_profile/sap_sids
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["sap_sids"] = ["ABC"]
    host_data["system_profile"]["workloads"] = {"sap": {}}
    host_data["system_profile"]["workloads"]["sap"]["sids"] = ["ABC"]
    host_inventory.kafka.create_host(host_data)

    url = service_proxy_url + "/system_profile/sap_sids"
    logger.info(f"REST: {url}")
    response = application.http_client.get(url)
    assert response.status_code == 200
    response = response.json()
    assert response["total"] >= 1
    assert len(response["results"]) == response["total"]
    found = False
    for sid in response["results"]:
        if sid["value"] == "ABC":
            assert sid["count"] >= 1
            found = True
            break
    assert found


@pytest.mark.ephemeral
def test_service_proxy_get_sap_system(
    application: Application,
    service_proxy_url: str,
    host_inventory: ApplicationHostInventory,
):
    """
    Test GET on /system_profile/sap_system endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-system_profile-get-sap_system
        assignee: fstavela
        importance: medium
        title: Test service proxy - GET /system_profile/sap_system
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["sap_system"] = True
    host_data["system_profile"]["workloads"] = {"sap": {}}
    host_data["system_profile"]["workloads"]["sap"]["sap_system"] = True
    host_inventory.kafka.create_host(host_data)

    url = service_proxy_url + "/system_profile/sap_system"
    logger.info(f"REST: {url}")
    response = application.http_client.get(url)
    assert response.status_code == 200
    response = response.json()
    assert response["total"] in (1, 2)
    assert len(response["results"]) == response["total"]
    found = False
    for sap_system in response["results"]:
        if sap_system["value"] is True:
            assert sap_system["count"] >= 1
            found = True
            break
    assert found


@pytest.mark.ephemeral
def test_service_proxy_get_tags(
    application: Application,
    service_proxy_url: str,
    host_inventory: ApplicationHostInventory,
):
    """
    Test GET on /tags endpoint using the service proxy (old port 8080)

    JIRA: https://issues.redhat.com/browse/ESSNTL-933

    metadata:
        requirements: inv-service-proxy, inv-tags-get-list
        assignee: fstavela
        importance: medium
        title: Test service proxy - GET /tags
    """
    host_data = host_inventory.datagen.create_host_data(tags=generate_tags(1))
    host = host_inventory.kafka.create_host(host_data)

    url = service_proxy_url + f"/tags?display_name={host.display_name}"
    logger.info(f"REST: {url}")
    response = application.http_client.get(url)
    assert response.status_code == 200
    response = response.json()
    assert response["total"] == 1
    assert len(response["results"]) == 1
    assert response["results"][0]["tag"] == host_data["tags"][0]
    assert response["results"][0]["count"] == 1
