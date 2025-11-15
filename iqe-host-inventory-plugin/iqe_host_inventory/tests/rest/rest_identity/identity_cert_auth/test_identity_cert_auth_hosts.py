from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import accept_when
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.fixture
def setup_owner_id_hosts(
    host_inventory: ApplicationHostInventory,
    host_inventory_identity_auth_system: ApplicationHostInventory,
    inventory_cert_system_owner_id: str,
) -> dict[str, HostWrapper]:
    # Cleanup
    host_inventory_identity_auth_system.apis.hosts.confirm_delete_all()

    hosts_data = host_inventory.datagen.create_n_hosts_data(3)
    hosts_data[0]["system_profile"].pop("owner_id", None)
    hosts_data[1]["system_profile"]["owner_id"] = generate_uuid()
    hosts_data[2]["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    return {
        "without_owner_id": hosts[0],
        "wrong_owner_id": hosts[1],
        "correct_owner_id": hosts[2],
    }


@pytest.fixture
def setup_hosts_with_facts(
    host_inventory: ApplicationHostInventory,
    inventory_cert_system_owner_id: str,
) -> dict[str, str | dict[str, str] | HostWrapper]:
    fact_namespace = "hbi-testing-patch"
    original_facts = {
        "fact1": "this should stay the same",
        "fact2": "this should be updated",
    }

    hosts_data = host_inventory.datagen.create_n_hosts_data(
        3, facts=[{"namespace": fact_namespace, "facts": original_facts}]
    )
    hosts_data[0]["system_profile"].pop("owner_id", None)
    hosts_data[1]["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    hosts_data[2]["system_profile"]["owner_id"] = generate_uuid()
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    return {
        "namespace": fact_namespace,
        "facts": original_facts,
        "without_owner_id": hosts[0],
        "correct_owner_id": hosts[1],
        "wrong_owner_id": hosts[2],
    }


@pytest.fixture(scope="class")
def setup_host_with_owner_id_secondary_class(
    host_inventory_secondary: ApplicationHostInventory,
    hbi_secondary_org_id: str,
    inventory_cert_system_owner_id: str,
) -> HostWrapper:
    fact_namespace = "hbi-testing-patch"
    facts = {
        "fact1": "original fact1",
        "fact2": "original fact2",
    }

    host_data = host_inventory_secondary.datagen.create_host_data()
    host_data["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    host_data["org_id"] = hbi_secondary_org_id
    host_data["tags"] = [gen_tag()]
    host_data["facts"] = [{"namespace": fact_namespace, "facts": facts}]

    return host_inventory_secondary.kafka.create_host(host_data=host_data, cleanup_scope="class")


def _first_fact_fetcher(
    host_inventory: ApplicationHostInventory, host_id: str
) -> Callable[[], tuple[str, dict[str, str]]]:
    def fetch_fact() -> tuple[str, dict[str, str]]:
        response = host_inventory.apis.hosts.get_hosts_by_id_response(host_id)
        response_facts = response.results[0].facts[0]
        return response_facts.namespace, response_facts.facts

    return fetch_fact


def _ensure_facts_update(host_inventory, host_id, namespace, facts):
    def facts_match(response: tuple[str, dict[str, str]]):
        return response == (namespace, facts)

    accept_when(_first_fact_fetcher(host_inventory, host_id), is_valid=facts_match)


def _ensure_facts_dont_update(host_inventory, host_id, namespace, facts, original):
    def facts_match(response_fact: tuple[str, dict[str, str]]):
        return namespace == response_fact[0] and facts == response_fact[1]

    fact = accept_when(
        _first_fact_fetcher(host_inventory, host_id), is_valid=facts_match, retries=3, error=None
    )
    assert fact[0] == namespace and fact[1] == original


@pytest.mark.ephemeral
def test_cert_auth_get_host_by_id(
    setup_owner_id_hosts,
    host_inventory_system_correct,
):
    """
    Test that I can only read data of the hosts with the same owner ID as my host has
    when using cert auth by trying to get host by ID.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-get-by-id
        assignee: fstavela
        importance: high
        title: Inventory: get host by ID using cert auth
    """
    hosts = setup_owner_id_hosts

    response = host_inventory_system_correct.apis.hosts.get_hosts_by_id_response([
        hosts["correct_owner_id"].id,
        hosts["without_owner_id"].id,
        hosts["wrong_owner_id"].id,
    ])
    assert response.count == 1
    assert response.results[0].id == hosts["correct_owner_id"].id


@pytest.mark.ephemeral
def test_cert_auth_get_host_by_display_name(
    setup_owner_id_hosts,
    host_inventory_system_correct,
):
    """
    Test that I can only read data of the hosts with the same owner ID as my host has when using
    cert auth by trying to get host by display name.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-filter-by-display_name
        assignee: fstavela
        importance: high
        title: Inventory: get host by display name using cert auth
    """
    hosts = setup_owner_id_hosts

    # Using host with the same owner ID
    response = host_inventory_system_correct.apis.hosts.get_hosts_response(
        display_name=hosts["correct_owner_id"].display_name
    )
    assert response.count == 1
    assert response.results[0].id == hosts["correct_owner_id"].id

    # Using host without owner ID
    response = host_inventory_system_correct.apis.hosts.get_hosts_response(
        display_name=hosts["without_owner_id"].display_name
    )
    assert response.count == 0

    # Using host with different owner ID
    response = host_inventory_system_correct.apis.hosts.get_hosts_response(
        display_name=hosts["wrong_owner_id"].display_name
    )
    assert response.count == 0


@pytest.mark.ephemeral
def test_cert_auth_get_all_hosts(
    setup_owner_id_hosts,
    host_inventory_system_correct,
):
    """
    Test that I can only read data of the hosts with the same owner ID as my host has
    when using cert auth by trying to get all hosts.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-get-list
        assignee: fstavela
        importance: high
        title: Inventory: get all hosts using cert auth
    """
    hosts = setup_owner_id_hosts

    response = host_inventory_system_correct.apis.hosts.get_hosts_response()
    assert response.count == 1
    assert response.results[0].id == hosts["correct_owner_id"].id


@pytest.mark.ephemeral
def test_cert_auth_get_host_system_profile(
    setup_owner_id_hosts,
    inventory_cert_system_owner_id,
    host_inventory_system_correct,
):
    """
    Test that I can only read data of the hosts with the same owner ID as my host has when using
    cert auth by trying to get host's system profile.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-get-system_profile
        assignee: fstavela
        importance: high
        title: Inventory: get host's system profile using cert auth
    """
    hosts = setup_owner_id_hosts

    response = host_inventory_system_correct.apis.hosts.get_hosts_system_profile_response([
        hosts["correct_owner_id"].id,
        hosts["without_owner_id"].id,
        hosts["wrong_owner_id"].id,
    ])
    assert response.count == 1
    assert response.results[0].id == hosts["correct_owner_id"].id
    assert response.results[0].system_profile.owner_id == inventory_cert_system_owner_id


@pytest.mark.ephemeral
def test_cert_auth_get_host_tags(
    hbi_setup_tagged_hosts_for_identity_cert_auth,
    host_inventory_system_correct,
):
    """
    Test that I can only read data of the hosts with the same owner ID as my host has when using
    cert auth by trying to get host's tags.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-get-tags
        assignee: fstavela
        importance: high
        title: Inventory: get host's tags using cert auth
    """
    hosts = hbi_setup_tagged_hosts_for_identity_cert_auth

    response = host_inventory_system_correct.apis.hosts.get_host_tags_response([
        hosts["correct_owner_id_host"].id,
        hosts["without_owner_id_host"].id,
        hosts["wrong_owner_id_host"].id,
    ])
    assert response.count == 1
    assert (
        response.results[hosts["correct_owner_id_host"].id][0].to_dict()
        == hosts["correct_owner_id_tag"]
    )


@pytest.mark.ephemeral
def test_cert_auth_get_host_tag_count(
    hbi_setup_tagged_hosts_for_identity_cert_auth,
    host_inventory_system_correct,
):
    """
    Test that I can only read data of the hosts with the same owner ID as my host has when using
    cert auth by trying to get host's tags count.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-get-tags-count
        assignee: fstavela
        importance: high
        title: Inventory: get host's tags count using cert auth
    """
    hosts = hbi_setup_tagged_hosts_for_identity_cert_auth

    response = host_inventory_system_correct.apis.hosts.get_host_tags_count_response([
        hosts["correct_owner_id_host"].id,
        hosts["without_owner_id_host"].id,
        hosts["wrong_owner_id_host"].id,
    ])
    assert response.count == 1
    assert response.results[hosts["correct_owner_id_host"].id] == 1


@pytest.mark.ephemeral
def test_cert_auth_patch_display_name(
    setup_owner_id_hosts,
    host_inventory_system_correct,
    host_inventory: ApplicationHostInventory,
):
    """
    Test that I can only update data of the hosts with the same owner ID as my host has when
    using cert auth by trying to patch display name.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-patch
        assignee: fstavela
        importance: high
        title: Inventory: patch display name using cert auth
    """
    hosts = setup_owner_id_hosts
    new_display_name = generate_display_name()
    # Using host with the same owner ID
    host_inventory_system_correct.apis.hosts.patch_hosts(
        hosts["correct_owner_id"].id, display_name=new_display_name
    )
    host_inventory.apis.hosts.wait_for_updated(
        hosts["correct_owner_id"], display_name=new_display_name
    )

    for wont_update in ("without_owner_id", "wrong_owner_id"):
        wont_update_host = hosts[wont_update]
        old_display_name = wont_update_host.display_name
        with raises_apierror(404):
            host_inventory_system_correct.apis.hosts.patch_hosts(
                wont_update_host.id, display_name=new_display_name, wait_for_updated=False
            )
        host_inventory.apis.hosts.verify_not_updated(
            wont_update_host, display_name=old_display_name
        )


@pytest.mark.ephemeral
def test_cert_auth_patch_facts(
    setup_hosts_with_facts: dict[str, Any],
    host_inventory: ApplicationHostInventory,
    host_inventory_system_correct: ApplicationHostInventory,
):
    """
    Test that I can only update data of the hosts with the same owner ID as my host has when
    using cert auth by trying to patch the facts.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-patch-facts
        assignee: fstavela
        importance: high
        title: Inventory: patch facts using cert auth
    """
    hosts = setup_hosts_with_facts
    new_facts = {"fact2": "updated fact"}

    # Using host with the same owner ID
    merged_facts = {**hosts["facts"], **new_facts}
    host_inventory_system_correct.apis.hosts.merge_facts(
        hosts["correct_owner_id"].id, hosts["namespace"], new_facts
    )
    _ensure_facts_update(
        host_inventory, hosts["correct_owner_id"].id, hosts["namespace"], merged_facts
    )

    # Using host without owner ID
    with raises_apierror(404):
        host_inventory_system_correct.apis.hosts.merge_facts(
            hosts["without_owner_id"].id, hosts["namespace"], new_facts
        )
    _ensure_facts_dont_update(
        host_inventory, hosts["without_owner_id"].id, hosts["namespace"], new_facts, hosts["facts"]
    )

    # Using host with different owner ID
    with raises_apierror(404):
        host_inventory_system_correct.apis.hosts.merge_facts(
            hosts["wrong_owner_id"].id, hosts["namespace"], new_facts
        )
    _ensure_facts_dont_update(
        host_inventory, hosts["wrong_owner_id"].id, hosts["namespace"], new_facts, hosts["facts"]
    )


@pytest.mark.ephemeral
def test_cert_auth_put_facts(
    setup_hosts_with_facts: dict[str, Any],
    host_inventory: ApplicationHostInventory,
    host_inventory_system_correct: ApplicationHostInventory,
):
    """
    Test that I can only update data of the hosts with the same owner ID as my host has when
    using cert auth by trying to put the facts.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-put-facts
        assignee: fstavela
        importance: high
        title: Inventory: put facts using cert auth
    """
    hosts = setup_hosts_with_facts
    new_facts = {"fact2": "updated fact"}

    # Using host with the same owner ID
    host_inventory_system_correct.apis.hosts.replace_facts(
        hosts["correct_owner_id"].id, namespace=hosts["namespace"], facts=new_facts
    )
    _ensure_facts_update(
        host_inventory, hosts["correct_owner_id"].id, hosts["namespace"], new_facts
    )

    # Using host without owner ID
    with raises_apierror(404):
        host_inventory_system_correct.apis.hosts.replace_facts(
            hosts["without_owner_id"].id, namespace=hosts["namespace"], facts=new_facts
        )
    _ensure_facts_dont_update(
        host_inventory, hosts["without_owner_id"].id, hosts["namespace"], new_facts, hosts["facts"]
    )

    # Using host with different owner ID
    with raises_apierror(404):
        host_inventory_system_correct.apis.hosts.replace_facts(
            hosts["wrong_owner_id"].id, namespace=hosts["namespace"], facts=new_facts
        )
    _ensure_facts_dont_update(
        host_inventory, hosts["wrong_owner_id"].id, hosts["namespace"], new_facts, hosts["facts"]
    )


@pytest.mark.ephemeral
def test_cert_auth_delete_host(
    setup_owner_id_hosts,
    host_inventory: ApplicationHostInventory,
    host_inventory_system_correct,
):
    """
    Test that I can delete the hosts with the same owner ID as my host has
    when using cert auth.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-delete-by-id
        assignee: fstavela
        importance: high
        title: Inventory: delete host using cert auth
    """
    hosts = setup_owner_id_hosts

    # Using host with the same owner ID
    host_inventory_system_correct.apis.hosts.delete_by_id_raw(hosts["correct_owner_id"].id)
    host_inventory.apis.hosts.wait_for_deleted(hosts["correct_owner_id"])

    # Using host without owner ID
    with raises_apierror(404):
        host_inventory_system_correct.apis.hosts.delete_by_id_raw(hosts["without_owner_id"].id)
    host_inventory.apis.hosts.verify_not_deleted(hosts["without_owner_id"])

    # Using host with different owner ID

    with raises_apierror(404):
        host_inventory_system_correct.apis.hosts.delete_by_id_raw(hosts["wrong_owner_id"].id)
    host_inventory.apis.hosts.verify_not_deleted(hosts["wrong_owner_id"])


@pytest.mark.ephemeral
def test_cert_auth_delete_multiple_hosts(
    setup_owner_id_hosts: dict[str, HostWrapper],
    inventory_cert_system_owner_id: str,
    host_inventory: ApplicationHostInventory,
    host_inventory_system_correct: ApplicationHostInventory,
):
    """
    Test that I can bulk delete the hosts with the same owner ID as my host
    when using cert auth

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-delete-by-id
        assignee: msager
        importance: high
        title: Inventory: delete multiple hosts using cert auth
    """
    # Setup a mix of accessible/inaccessible hosts
    hosts = setup_owner_id_hosts

    deleted_ids = {hosts["correct_owner_id"].id}
    not_deleted_ids = {hosts["without_owner_id"].id, hosts["wrong_owner_id"].id}

    # Add a couple more accessible hosts
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    hosts_data[0]["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    hosts_data[1]["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    more_hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    assert len(more_hosts) == 2

    deleted_ids.update([more_hosts[0].id, more_hosts[1].id])

    # Attempt a bulk delete of all hosts.  Only the accessible hosts should be deleted.
    host_inventory_system_correct.apis.hosts.delete_filtered(staleness="fresh")

    remaining_hosts = host_inventory.apis.hosts.get_hosts()
    remaining_host_ids = {host.id for host in remaining_hosts}

    assert remaining_host_ids & not_deleted_ids == not_deleted_ids
    assert len(remaining_host_ids & deleted_ids) == 0


@pytest.mark.ephemeral
def test_cert_auth_delete_all_hosts(
    setup_owner_id_hosts: dict[str, HostWrapper],
    inventory_cert_system_owner_id: str,
    host_inventory: ApplicationHostInventory,
    host_inventory_system_correct: ApplicationHostInventory,
):
    """
    Test that I can delete all the hosts with the same owner ID as my host
    when using cert auth

    metadata:
        requirements: inv-api-cert-auth, inv-hosts-delete-all
        assignee: msager
        importance: high
        title: Inventory: delete all hosts using cert auth
    """
    # Setup a mix of accessible/inaccessible hosts
    hosts = setup_owner_id_hosts

    not_deleted_ids = {hosts["without_owner_id"].id, hosts["wrong_owner_id"].id}

    # Add a couple more accessible hosts
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    hosts_data[0]["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    hosts_data[1]["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    more_hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    assert len(more_hosts) == 2

    # Attempt to delete all hosts.  Only the accessible hosts should be deleted.
    host_inventory_system_correct.apis.hosts.confirm_delete_all()

    host_inventory.apis.hosts.wait_for_deleted([hosts["correct_owner_id"], *more_hosts])
    host_inventory_system_correct.apis.hosts.wait_for_all_deleted()

    remaining_hosts = host_inventory.apis.hosts.get_hosts()
    remaining_host_ids = {host.id for host in remaining_hosts}
    assert all(host_id in remaining_host_ids for host_id in not_deleted_ids)


@pytest.mark.ephemeral
def test_cert_auth_export_hosts(
    setup_owner_id_hosts,
    host_inventory_system_correct,
):
    """
    Test that I can only export hosts with the same owner ID as my host has
    when using cert auth

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417
          https://issues.redhat.com/browse/RHCLOUD-34799

    metadata:
        requirements: inv-api-cert-auth, inv-export-hosts
        assignee: msager
        importance: high
        title: Inventory: Export hosts using cert auth
    """
    hosts = setup_owner_id_hosts
    report = host_inventory_system_correct.apis.exports.export_hosts()

    assert len(report) == 1
    assert report[0]["host_id"] == hosts["correct_owner_id"].id


@pytest.mark.ephemeral
def test_cert_auth_get_host_exists(
    setup_owner_id_hosts,
    host_inventory_system_correct,
):
    """
    Test that I can only check a host's existence with the same owner ID as my host has
    when using cert auth

    JIRA: https://issues.redhat.com/browse/RHCLOUD-10417
          https://issues.redhat.com/browse/RHCLOUD-34799

    metadata:
        requirements: inv-api-cert-auth, inv-host_exists-get-by-insights-id
        assignee: msager
        importance: high
        title: Inventory: Check a host's existence using cert auth
    """
    hosts = setup_owner_id_hosts

    insights_id = hosts["correct_owner_id"].insights_id
    response = host_inventory_system_correct.apis.hosts.get_host_exists(insights_id)
    assert response.id == hosts["correct_owner_id"].id

    insights_id = hosts["without_owner_id"].insights_id
    with raises_apierror(404, match_message=f"No host found for Insights ID '{insights_id}'"):
        host_inventory_system_correct.apis.hosts.get_host_exists(insights_id)

    insights_id = hosts["wrong_owner_id"].insights_id
    with raises_apierror(404, match_message=f"No host found for Insights ID '{insights_id}'"):
        host_inventory_system_correct.apis.hosts.get_host_exists(insights_id)


class TestCertAuthHostsDifferentAccount:
    @pytest.mark.ephemeral
    def test_cert_auth_get_host_by_id_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
    ):
        """
        Test that I can't get a host by id from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-get-by-id
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to get host by id from a different account using cert auth
        """
        host = setup_host_with_owner_id_secondary_class

        response = host_inventory_identity_auth_system.apis.hosts.get_hosts_by_id_response(host.id)
        assert response.count == 0

    @pytest.mark.ephemeral
    def test_cert_auth_get_host_by_display_name_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
    ):
        """
        Test that I can't get a host by display name from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-filter-by-display_name
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to get host by display name from a different account using
                cert auth
        """
        host = setup_host_with_owner_id_secondary_class

        response = host_inventory_identity_auth_system.apis.hosts.get_hosts_response(
            display_name=host.display_name
        )
        assert response.count == 0

    @pytest.mark.ephemeral
    def test_cert_auth_get_all_hosts_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
    ):
        """
        Test that I can't get hosts from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-get-list
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to get hosts from a different account using cert auth
        """
        response = host_inventory_identity_auth_system.apis.hosts.get_hosts_response()
        assert response.count == 0

    @pytest.mark.ephemeral
    def test_cert_auth_get_host_system_profile_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
    ):
        """
        Test that I can't get a host's system profile from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-get-system_profile
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to get a host's system profile from a different account using
                cert auth
        """
        host = setup_host_with_owner_id_secondary_class

        response = (
            host_inventory_identity_auth_system.apis.hosts.get_hosts_system_profile_response(
                host.id
            )
        )
        assert response.count == 0

    @pytest.mark.ephemeral
    def test_cert_auth_get_host_tags_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
    ):
        """
        Test that I can't get a host's tags from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-get-tags
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to get a host's tags from a different account using cert auth
        """
        host = setup_host_with_owner_id_secondary_class

        response = host_inventory_identity_auth_system.apis.hosts.get_host_tags_response(host.id)
        assert response.count == 0

    @pytest.mark.ephemeral
    def test_cert_auth_get_host_tag_count_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
    ):
        """
        Test that I can't get a host tag's count from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-get-tags-count
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to get a host tag's count from a different account using
                cert auth
        """
        host = setup_host_with_owner_id_secondary_class

        response = host_inventory_identity_auth_system.apis.hosts.get_host_tags_count_response(
            host.id
        )
        assert response.count == 0

    @pytest.mark.ephemeral
    def test_cert_auth_patch_display_name_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
        host_inventory_secondary: ApplicationHostInventory,
    ):
        """
        Test that I can't update a host from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-patch
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to update a host from a different account using cert auth
        """
        host = setup_host_with_owner_id_secondary_class
        old_display_name = host.display_name

        new_display_name = generate_display_name()

        with raises_apierror(404):
            host_inventory_identity_auth_system.apis.hosts.patch_hosts(
                host.id, display_name=new_display_name, wait_for_updated=False
            )

        host_inventory_secondary.apis.hosts.verify_not_updated(
            host.id, display_name=old_display_name
        )

    @pytest.mark.ephemeral
    def test_cert_auth_patch_facts_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
        host_inventory_secondary: ApplicationHostInventory,
    ):
        """
        Test that I can't patch host data from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-patch-facts
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to patch host data from a different account using cert auth
        """
        host = setup_host_with_owner_id_secondary_class
        namespace = host.facts[0]["namespace"]
        original_facts = host.facts[0]["facts"]

        new_facts = {"fact1": "updated fact1", "fact2": "updated fact2"}

        with raises_apierror(404):
            host_inventory_identity_auth_system.apis.hosts.merge_facts(
                host.id, namespace, new_facts
            )

        _ensure_facts_dont_update(
            host_inventory_secondary, host.id, namespace, new_facts, original_facts
        )

    @pytest.mark.ephemeral
    def test_cert_auth_put_facts_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
        host_inventory_secondary: ApplicationHostInventory,
    ):
        """
        Test that I can't replace host data from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-put-facts
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to replace host data from a different account using cert auth
        """
        host = setup_host_with_owner_id_secondary_class
        namespace = host.facts[0]["namespace"]
        original_facts = host.facts[0]["facts"]

        new_facts = {"fact1": "updated fact1", "fact2": "updated fact2"}

        with raises_apierror(404):
            host_inventory_identity_auth_system.apis.hosts.replace_facts(
                host.id, namespace, new_facts
            )

        _ensure_facts_dont_update(
            host_inventory_secondary, host.id, namespace, new_facts, original_facts
        )

    @pytest.mark.ephemeral
    def test_cert_auth_delete_host_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
        host_inventory_secondary: ApplicationHostInventory,
    ):
        """
        Test that I can't delete a host from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-hosts-delete-by-id
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to delete a host from a different account using cert auth
        """
        host = setup_host_with_owner_id_secondary_class

        with raises_apierror(404):
            host_inventory_identity_auth_system.apis.hosts.delete_by_id_raw(host.id)

        host_inventory_secondary.apis.hosts.verify_not_deleted(host.id)

    @pytest.mark.ephemeral
    def test_cert_auth_get_host_exists_different_account(
        self,
        setup_host_with_owner_id_secondary_class: HostWrapper,
        host_inventory_identity_auth_system: ApplicationHostInventory,
    ):
        """
        Test that I can't check a host's existence from a different account when using cert auth

        metadata:
            requirements: inv-api-cert-auth, inv-host_exists-get-by-insights-id
            assignee: msager
            importance: high
            negative: true
            title: Inventory: attempt to check a host's existence from a different account using
                cert auth
        """
        host = setup_host_with_owner_id_secondary_class

        with raises_apierror(404):
            host_inventory_identity_auth_system.apis.hosts.get_host_exists(host.insights_id)
