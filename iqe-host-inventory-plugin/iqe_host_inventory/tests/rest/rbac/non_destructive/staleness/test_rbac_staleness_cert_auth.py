# mypy: disallow-untyped-defs

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.staleness_utils import get_staleness_fields

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent, pytest.mark.cert_auth]


@pytest.mark.usefixtures("rbac_staleness_all_hosts_all_user_setup_class")
class TestRBACStalenessCertAuth:
    def test_rbac_staleness_cert_auth_bypass_checks_get_staleness_defaults(
        self,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a cert-auth client tries to get the staleness defaults via REST API

        1. Issue a GET request on /account/staleness/defaults
        2. Ensure GET request returns a 403 error

        metadata:
            assignee: msager
            importance: medium
            negative: true
            title: Test that you can't access staleness defaults with cert auth
        """
        staleness_api = host_inventory_non_org_admin_cert_auth.apis.account_staleness
        resp = staleness_api.get_default_staleness_response()
        assert resp.status_code == 403

    def test_rbac_staleness_cert_auth_bypass_checks_get_staleness(
        self,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a cert-auth client tries to get the staleness settings via REST API

        1. Issue a GET request on /account/staleness
        2. Ensure GET request returns a 403 error

        metadata:
            assignee: msager
            importance: medium
            negative: true
            title: Test that you can't access staleness settings with cert auth
        """
        staleness = host_inventory_non_org_admin_cert_auth.apis.account_staleness
        resp = staleness.get_staleness_response()
        assert resp.status_code == 403

    def test_rbac_staleness_cert_auth_bypass_checks_create_staleness(
        self,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a cert-auth client tries to create staleness settings via REST API

        1. Issue a POST request on /account/staleness
        2. Ensure POST request returns a 403 error

        metadata:
            assignee: msager
            importance: medium
            negative: true
            title: Test that you can't create staleness settings with cert auth
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))

        resp = host_inventory_non_org_admin_cert_auth.apis.account_staleness.create_staleness(
            **settings
        )
        assert resp.status_code == 403

    @pytest.mark.usefixtures("hbi_staleness_cleanup")
    def test_rbac_staleness_cert_auth_bypass_checks_update_staleness(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a cert-auth client tries to update staleness settings via REST API

        1. Issue a POST request on /account/staleness to create the staleness settings
        2. Issue a PATCH request on /account/staleness
        3. Ensure PATCH request returns a 403 error

        metadata:
            assignee: msager
            importance: medium
            negative: true
            title: Test that you can't update staleness defaults with cert auth
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        host_inventory.apis.account_staleness.create_staleness(**settings).json()

        settings = dict(zip(get_staleness_fields(), [4, 5, 6], strict=False))
        resp = host_inventory_non_org_admin_cert_auth.apis.account_staleness.update_staleness(
            **settings
        )
        assert resp.status_code == 403

    @pytest.mark.usefixtures("hbi_staleness_cleanup")
    def test_rbac_staleness_cert_auth_bypass_checks_delete_staleness(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a cert-auth client tries to delete staleness settings via REST API

        1. Issue a POST request on /account/staleness to create settings
        2. Issue a DELETE request on /account/staleness
        3. Ensure DELETE request returns a 403 error

        metadata:
            assignee: msager
            importance: medium
            negative: true
            title: Test that you can't delete staleness settings with cert auth
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        host_inventory.apis.account_staleness.create_staleness(**settings).json()

        resp = host_inventory_non_org_admin_cert_auth.apis.account_staleness.delete_staleness()
        assert resp.status_code == 403
