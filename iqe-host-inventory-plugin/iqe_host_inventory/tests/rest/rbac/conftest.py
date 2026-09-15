import pytest

from iqe_host_inventory.tests import _rbac_state


@pytest.fixture(autouse=True)
def _skip_if_rbac_setup_failed():
    """Skip RBAC tests when pre-configured role setup failed during session init."""
    if _rbac_state.rbac_setup_failed is not None:
        pytest.skip(f"RBAC setup failed: {_rbac_state.rbac_setup_failed}")
