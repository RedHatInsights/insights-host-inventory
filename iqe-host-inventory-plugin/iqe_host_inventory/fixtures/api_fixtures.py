from __future__ import annotations

import logging

import pytest
from iqe.base.application import Application

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import delete_hosts
from iqe_host_inventory.utils.datagen_utils import create_system_profile_facts
from iqe_host_inventory_api import HostsApi
from iqe_host_inventory_api import TagsApi

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def openapi_client(application: Application) -> HostsApi:
    return application.host_inventory.rest_client.hosts_api


@pytest.fixture(scope="session")
def openapi_client_tags(application: Application) -> TagsApi:
    return application.host_inventory.rest_client.tags_api


@pytest.fixture(scope="session")
def example_system_profile_facts() -> dict[str, str | int | list]:
    return create_system_profile_facts()


@pytest.fixture(scope="session")
def hbi_legacy_hostname(application: Application) -> str:
    return application.host_inventory.config.legacy_hostname


@pytest.fixture(scope="session")
def hbi_legacy_cert_hostname(hbi_legacy_hostname: str) -> str:
    return "cert-" + hbi_legacy_hostname


@pytest.fixture(scope="session")
def hbi_ephemeral_base_url(host_inventory: ApplicationHostInventory) -> str:
    inventory_conf = host_inventory.config.get("service_objects").get("api").get("config")
    return (
        f"{inventory_conf.get('scheme')}://{inventory_conf.get('hostname')}:"
        f"{inventory_conf.get('port')}"
    )


@pytest.fixture(scope="session")
def hbi_base_url(application: Application, hbi_ephemeral_base_url: str) -> str:
    # Check if we are in an ephemeral environment
    if application.user_provider_keycloak:
        return hbi_ephemeral_base_url
    return f"https://{application.config.MAIN.hostname}"


@pytest.fixture
def hbi_empty_database(openapi_client: HostsApi) -> None:
    response = openapi_client.api_host_get_host_list(staleness=["fresh", "stale", "stale_warning"])
    while response.count:
        delete_hosts(response.results, openapi_client)
        response = openapi_client.api_host_get_host_list(
            staleness=["fresh", "stale", "stale_warning"]
        )
