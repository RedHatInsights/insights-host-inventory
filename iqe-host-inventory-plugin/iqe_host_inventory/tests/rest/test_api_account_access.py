# mypy: disallow-untyped-defs

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
@pytest.mark.multi_account
def test_access_host_from_another_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_upload_prepare_host_module: HostOut,
) -> None:
    """
    Test accessing a host from another account.

    Confirm that a user trying to access a host associated with another account does not have
    access to the host.

    1. Create a host using the primary account
    2. Fetch the created host using the primary account
    3. Fetch the host using the secondary account and confirm the information is not accessible.

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: critical
        title: Inventory: confirm hosts cannot be accessed from another account
    """
    # Creates a host using the main account
    host = hbi_upload_prepare_host_module

    # Fetch the host using the main account
    main_account_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id)
    assert main_account_host.results
    assert str(main_account_host.results[0].org_id) == str(hbi_default_org_id)

    # Fetch the host using the secondary account
    with raises_apierror(404):
        host_inventory_secondary.apis.hosts.get_hosts_by_id_response(host.id)

    response = host_inventory_secondary.apis.hosts.get_hosts_response(hostname_or_id=host.id)
    assert not response.total

    response = host_inventory_secondary.apis.hosts.get_hosts_response(
        hostname_or_id=host.display_name
    )
    assert not response.total


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
@pytest.mark.multi_account
def test_delete_multiple_accounts(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_upload_prepare_host_module: HostOut,
) -> None:
    """
    Test deletion from another account.

    Confirm that a user trying to delete hosts associated with another account cannot.

    1. Create a host using the primary account
    2. Fetch the created host using the secondary account and confirm the results are 0.
    3. Attempt to delete the hosts using the secondary account and confirm the delete operation
    fails.

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: critical
        title: Inventory: Deletion from another account should fail with 404
    """
    host = hbi_upload_prepare_host_module

    prim_hosts = host_inventory.apis.hosts.get_hosts_by_id_response(host)
    assert len(prim_hosts.results) == 1

    with raises_apierror(404):
        host_inventory_secondary.apis.hosts.delete_by_id_raw(host.id)

    host_inventory.apis.hosts.verify_not_deleted(host)


@pytest.mark.smoke
def test_access_other_orgs_with_org_id_header(
    host_inventory_secondary: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_secondary_org_id: str,
    is_kessel_phase_1_enabled: bool,
    hbi_upload_prepare_host_module: HostOut,
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-18446

    metadata:
        requirements: inv-account-integrity, inv-rhsm-org_id-header
        assignee: fstavela
        importance: critical
        title: Test that org-id header is ignored on requests that aren't coming from internal RHSM
    """
    host = hbi_upload_prepare_host_module

    with temp_headers(
        host_inventory_secondary.apis.hosts.raw_api, {"x-inventory-org-id": hbi_default_org_id}
    ):
        response_hosts = host_inventory_secondary.apis.hosts.get_hosts()
        assert all(h.org_id == hbi_secondary_org_id for h in response_hosts)
        assert host.id not in [h.id for h in response_hosts]

    with raises_apierror(404):
        host_inventory_secondary.apis.hosts.get_hosts_by_id(host)
