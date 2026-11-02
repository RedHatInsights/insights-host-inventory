# mypy: disallow-untyped-defs

from collections.abc import Callable
from uuid import UUID

import pytest

from app.models import Host
from app.utils import HostWrapper
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import generate_random_string
from tests.helpers.test_utils import minimal_host


@pytest.mark.parametrize("reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_update_display_name_ignored_after_created_by_puptoo(
    mq_create_or_update_host: Callable[..., HostWrapper],
    db_get_host: Callable[[UUID | str], Host | None],
    reporter: str,
) -> None:
    # Create a host with display_name as puptoo
    original_display_name = generate_random_string()
    host_data = minimal_host(reporter="puptoo", display_name=original_display_name)
    host = mq_create_or_update_host(host_data)
    assert host.display_name == original_display_name

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "puptoo"

    # Try to update the display_name as RHSM
    host_data.display_name = generate_random_string()
    host_data.reporter = reporter
    updated_host = mq_create_or_update_host(host_data)
    assert updated_host.display_name == original_display_name
    assert updated_host.reporter == reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "puptoo"
    assert db_host.display_name == original_display_name
    assert db_host.reporter == reporter


@pytest.mark.parametrize("reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_update_display_name_ignored_after_updated_by_puptoo(
    mq_create_or_update_host: Callable[..., HostWrapper],
    db_get_host: Callable[[UUID | str], Host | None],
    reporter: str,
) -> None:
    # Create a host without setting the display_name
    host_data = minimal_host(reporter=reporter)
    host = mq_create_or_update_host(host_data)
    assert host.display_name == host.id
    assert host.reporter == reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter is None

    # Update the display_name as puptoo
    puptoo_display_name = generate_random_string()
    host_data.display_name = puptoo_display_name
    host_data.reporter = "puptoo"
    updated_host = mq_create_or_update_host(host_data)
    assert updated_host.display_name == puptoo_display_name
    assert updated_host.reporter == "puptoo"

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "puptoo"
    assert db_host.display_name == puptoo_display_name
    assert db_host.reporter == "puptoo"

    # Try to update the display_name as RHSM
    host_data.display_name = generate_random_string()
    host_data.reporter = reporter
    updated_host = mq_create_or_update_host(host_data)
    assert updated_host.display_name == puptoo_display_name
    assert updated_host.reporter == reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "puptoo"
    assert db_host.display_name == puptoo_display_name
    assert db_host.reporter == reporter


@pytest.mark.parametrize(
    "orig_reporter",
    (
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "rhsm-conduit",
        "rhsm-system-profile-bridge",
        "cloud-connector",
        "test-reporter",
    ),
)
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_update_display_name_ignored_after_updated_by_api(
    mq_create_or_update_host: Callable[..., HostWrapper],
    db_get_host: Callable[[UUID | str], Host | None],
    api_patch: Callable[..., tuple[int, dict]],
    orig_reporter: str,
    rhsm_reporter: str,
) -> None:
    # Create a host without setting the display_name
    host_data = minimal_host(reporter=orig_reporter)
    host = mq_create_or_update_host(host_data)
    assert host.display_name == host.id
    assert host.reporter == orig_reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter is None

    # Update the display_name via API
    api_display_name = generate_random_string()
    data = {"display_name": api_display_name}
    url = build_hosts_url(host_list_or_id=host.id)
    patch_response_status, _ = api_patch(url, data)
    assert_response_status(patch_response_status, expected_status=200)

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "API"
    assert db_host.display_name == api_display_name
    assert db_host.reporter == orig_reporter

    # Try to update the display_name as RHSM
    host_data.display_name = generate_random_string()
    host_data.reporter = rhsm_reporter
    updated_host = mq_create_or_update_host(host_data)
    assert updated_host.display_name == api_display_name
    assert updated_host.reporter == rhsm_reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "API"
    assert db_host.display_name == api_display_name
    assert db_host.reporter == rhsm_reporter


@pytest.mark.parametrize(
    "orig_reporter",
    (
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "rhsm-conduit",
        "rhsm-system-profile-bridge",
        "cloud-connector",
        "test-reporter",
    ),
)
@pytest.mark.parametrize("rhsm_reporter", ("rhsm-conduit", "rhsm-system-profile-bridge"))
def test_rhsm_update_display_name_accepted(
    mq_create_or_update_host: Callable[..., HostWrapper],
    db_get_host: Callable[[UUID | str], Host | None],
    orig_reporter: str,
    rhsm_reporter: str,
) -> None:
    # Create a host with display_name
    original_display_name = generate_random_string()
    host_data = minimal_host(reporter=orig_reporter, display_name=original_display_name)
    host = mq_create_or_update_host(host_data)
    assert host.display_name == original_display_name

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == orig_reporter

    # Check that RHSM can update the display_name, if it was not set by puptoo or API
    new_display_name = generate_random_string()
    host_data.display_name = new_display_name
    host_data.reporter = rhsm_reporter
    updated_host = mq_create_or_update_host(host_data)
    assert updated_host.display_name == new_display_name
    assert updated_host.reporter == rhsm_reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == rhsm_reporter
    assert db_host.display_name == new_display_name
    assert db_host.reporter == rhsm_reporter


@pytest.mark.parametrize(
    "reporter",
    (
        "puptoo",
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "rhsm-conduit",
        "rhsm-system-profile-bridge",
        "cloud-connector",
        "test-reporter",
    ),
)
@pytest.mark.parametrize("explicit_display_name", (True, False))
def test_update_display_name_by_api(
    mq_create_or_update_host: Callable[..., HostWrapper],
    db_get_host: Callable[[UUID | str], Host | None],
    api_patch: Callable[..., tuple[int, dict]],
    reporter: str,
    explicit_display_name: bool,
) -> None:
    # Create a host
    host_data = minimal_host(reporter=reporter)
    if explicit_display_name:
        host_data.display_name = generate_random_string()
    host = mq_create_or_update_host(host_data)

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == (reporter if explicit_display_name else None)

    # Check that we can always update the display_name via API, after any reporter
    api_display_name = generate_random_string()
    data = {"display_name": api_display_name}
    url = build_hosts_url(host_list_or_id=host.id)
    patch_response_status, _ = api_patch(url, data)
    assert_response_status(patch_response_status, expected_status=200)

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "API"
    assert db_host.display_name == api_display_name
    assert db_host.reporter == reporter

    # Check that we can update the display_name via API even after it was already updated by API
    new_display_name = generate_random_string()
    data = {"display_name": new_display_name}
    url = build_hosts_url(host_list_or_id=host.id)
    patch_response_status, _ = api_patch(url, data)
    assert_response_status(patch_response_status, expected_status=200)

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "API"
    assert db_host.display_name == new_display_name
    assert db_host.reporter == reporter


@pytest.mark.parametrize(
    "reporter",
    (
        "puptoo",
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "cloud-connector",
        "test-reporter",
    ),
)
def test_update_display_name_by_reporter_after_puptoo(
    mq_create_or_update_host: Callable[..., HostWrapper],
    db_get_host: Callable[[UUID | str], Host | None],
    reporter: str,
) -> None:
    # Create a host with display_name as puptoo
    original_display_name = generate_random_string()
    host_data = minimal_host(reporter="puptoo", display_name=original_display_name)
    host = mq_create_or_update_host(host_data)
    assert host.display_name == original_display_name

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "puptoo"

    # Check that we can update the display_name as any reporter except RHSM
    new_display_name = generate_random_string()
    host_data.display_name = new_display_name
    host_data.reporter = reporter
    updated_host = mq_create_or_update_host(host_data)
    assert updated_host.display_name == new_display_name
    assert updated_host.reporter == reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == reporter
    assert db_host.display_name == new_display_name
    assert db_host.reporter == reporter


@pytest.mark.parametrize(
    "orig_reporter",
    (
        "puptoo",
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "rhsm-conduit",
        "rhsm-system-profile-bridge",
        "cloud-connector",
        "test-reporter",
    ),
)
@pytest.mark.parametrize(
    "new_reporter",
    (
        "puptoo",
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "cloud-connector",
        "test-reporter",
    ),
)
def test_update_display_name_by_reporter_after_api(
    mq_create_or_update_host: Callable[..., HostWrapper],
    db_get_host: Callable[[UUID | str], Host | None],
    api_patch: Callable[..., tuple[int, dict]],
    orig_reporter: str,
    new_reporter: str,
) -> None:
    # Create a host without setting the display_name
    host_data = minimal_host(reporter=orig_reporter)
    host = mq_create_or_update_host(host_data)
    assert host.display_name == host.id
    assert host.reporter == orig_reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter is None

    # Update the display_name via API
    api_display_name = generate_random_string()
    data = {"display_name": api_display_name}
    url = build_hosts_url(host_list_or_id=host.id)
    patch_response_status, _ = api_patch(url, data)
    assert_response_status(patch_response_status, expected_status=200)

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == "API"
    assert db_host.display_name == api_display_name
    assert db_host.reporter == orig_reporter

    # Check that we can update the display_name as any reporter except RHSM
    new_display_name = generate_random_string()
    host_data.display_name = new_display_name
    host_data.reporter = new_reporter
    updated_host = mq_create_or_update_host(host_data)
    assert updated_host.display_name == new_display_name
    assert updated_host.reporter == new_reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == new_reporter
    assert db_host.display_name == new_display_name
    assert db_host.reporter == new_reporter


@pytest.mark.parametrize(
    "orig_reporter",
    (
        "puptoo",
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "rhsm-conduit",
        "rhsm-system-profile-bridge",
        "cloud-connector",
        "test-reporter",
    ),
)
@pytest.mark.parametrize(
    "new_reporter",
    (
        "puptoo",
        "yupana",
        "yuptoo",
        "satellite",
        "discovery",
        "rhsm-conduit",
        "rhsm-system-profile-bridge",
        "cloud-connector",
        "test-reporter",
    ),
)
def test_update_implicit_display_name_by_reporter(
    mq_create_or_update_host: Callable[..., HostWrapper],
    db_get_host: Callable[[UUID | str], Host | None],
    orig_reporter: str,
    new_reporter: str,
) -> None:
    # Create a host without setting the display_name
    host_data = minimal_host(reporter=orig_reporter)
    host = mq_create_or_update_host(host_data)
    assert host.display_name == host.id
    assert host.reporter == orig_reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter is None

    # Check that we can update the display_name as any reporter if it was set implicitly
    new_display_name = generate_random_string()
    host_data.display_name = new_display_name
    host_data.reporter = new_reporter
    updated_host = mq_create_or_update_host(host_data)
    assert updated_host.display_name == new_display_name
    assert updated_host.reporter == new_reporter

    db_host = db_get_host(host.id)
    assert db_host
    assert db_host.display_name_reporter == new_reporter
    assert db_host.display_name == new_display_name
    assert db_host.reporter == new_reporter
