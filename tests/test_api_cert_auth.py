# mypy: disallow-untyped-defs

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import pytest

from app.models import Host
from app.models.group import Group
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_facts_url
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import build_host_exists_url
from tests.helpers.api_utils import build_host_tags_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_operating_system_url
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import build_tags_count_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.db_utils import db_host
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid

OWNER_ID = SYSTEM_IDENTITY["system"]["cn"]
WRONG_OWNER_ID = generate_uuid()
OTHER_ORG_ID = "other-org"

SHARED_DISPLAY_NAME = "cert-auth-host"
SHARED_SYSTEM_PROFILE = {
    "operating_system": {"name": "RHEL", "major": 9, "minor": 2},
    "sap_system": True,
    "sap_sids": ["HBI"],
}


@dataclass
class HostRef:
    """Snapshot of host attributes captured immediately after creation to avoid DetachedInstanceError."""

    id: UUID
    insights_id: str
    display_name: str


@dataclass
class CertAuthHosts:
    no_owner: HostRef
    wrong_owner: HostRef
    accessible: HostRef
    other_org: HostRef

    @property
    def inaccessible(self) -> tuple[HostRef, HostRef, HostRef]:
        return self.no_owner, self.wrong_owner, self.other_org


def _snapshot(host: Host) -> HostRef:
    return HostRef(id=host.id, insights_id=host.insights_id, display_name=host.display_name)


@pytest.fixture
def setup_cert_auth_hosts(db_create_host: Callable[..., Host]) -> CertAuthHosts:
    """Create 4 hosts for cert auth testing. Only host_accessible should be visible."""
    return CertAuthHosts(
        no_owner=_snapshot(
            db_create_host(
                host=db_host(
                    display_name=SHARED_DISPLAY_NAME,
                    tags={"cert-test": {"tag": ["no-owner"]}},
                    system_profile_facts={**SHARED_SYSTEM_PROFILE, "owner_id": None},
                ),
            )
        ),
        wrong_owner=_snapshot(
            db_create_host(
                host=db_host(
                    display_name=SHARED_DISPLAY_NAME,
                    tags={"cert-test": {"tag": ["wrong-owner"]}},
                    system_profile_facts={**SHARED_SYSTEM_PROFILE, "owner_id": WRONG_OWNER_ID},
                ),
            )
        ),
        accessible=_snapshot(
            db_create_host(
                host=db_host(
                    display_name=SHARED_DISPLAY_NAME,
                    tags={"cert-test": {"tag": ["accessible"]}},
                    system_profile_facts={**SHARED_SYSTEM_PROFILE, "owner_id": OWNER_ID},
                ),
            )
        ),
        other_org=_snapshot(
            db_create_host(
                host=db_host(
                    org_id=OTHER_ORG_ID,
                    display_name=SHARED_DISPLAY_NAME,
                    tags={"cert-test": {"tag": ["other-org"]}},
                    system_profile_facts={**SHARED_SYSTEM_PROFILE, "owner_id": OWNER_ID},
                ),
            )
        ),
    )


# --- Read operations ---


def test_cert_auth_get_host_by_id(
    setup_cert_auth_hosts: CertAuthHosts,
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_get(build_hosts_url(host_list_or_id=hosts.accessible.id), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(hosts.accessible.id)

    for host in hosts.inaccessible:
        response_status, _ = api_get(build_hosts_url(host_list_or_id=host.id), SYSTEM_IDENTITY)
        assert_response_status(response_status, 404)


def test_cert_auth_get_host_by_display_name(
    setup_cert_auth_hosts: CertAuthHosts,
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_get(
        build_hosts_url(query=f"?display_name={SHARED_DISPLAY_NAME}"), SYSTEM_IDENTITY
    )
    assert_response_status(response_status, 200)
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(hosts.accessible.id)


def test_cert_auth_get_all_hosts(
    setup_cert_auth_hosts: CertAuthHosts,
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_get(build_hosts_url(), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(hosts.accessible.id)


def test_cert_auth_get_host_system_profile(
    setup_cert_auth_hosts: CertAuthHosts,
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_get(build_system_profile_url(hosts.accessible.id), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["count"] == 1
    profile = response_data["results"][0]["system_profile"]
    assert profile["owner_id"] == OWNER_ID

    for host in hosts.inaccessible:
        response_status, _ = api_get(build_system_profile_url(host.id), SYSTEM_IDENTITY)
        assert_response_status(response_status, 404)


def test_cert_auth_get_host_tags(
    setup_cert_auth_hosts: CertAuthHosts,
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_get(build_host_tags_url(hosts.accessible.id), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["count"] == 1

    for host in hosts.inaccessible:
        response_status, _ = api_get(build_host_tags_url(host.id), SYSTEM_IDENTITY)
        assert_response_status(response_status, 404)


def test_cert_auth_get_host_tag_count(
    setup_cert_auth_hosts: CertAuthHosts,
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_get(build_tags_count_url(hosts.accessible.id), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["count"] == 1

    for host in hosts.inaccessible:
        response_status, _ = api_get(build_tags_count_url(host.id), SYSTEM_IDENTITY)
        assert_response_status(response_status, 404)


def test_cert_auth_get_host_exists(
    setup_cert_auth_hosts: CertAuthHosts,
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_get(build_host_exists_url(hosts.accessible.insights_id), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["id"] == str(hosts.accessible.id)

    for host in hosts.inaccessible:
        response_status, _ = api_get(build_host_exists_url(host.insights_id), SYSTEM_IDENTITY)
        assert_response_status(response_status, 404)


@pytest.mark.usefixtures("setup_cert_auth_hosts")
def test_cert_auth_get_tags(
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    response_status, response_data = api_get(build_tags_url(), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    tag_values = [item["tag"]["value"] for item in response_data["results"]]
    assert "accessible" in tag_values
    assert "no-owner" not in tag_values
    assert "wrong-owner" not in tag_values
    assert "other-org" not in tag_values


@pytest.mark.usefixtures("setup_cert_auth_hosts")
def test_cert_auth_search_tags(
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    response_status, response_data = api_get(build_tags_url(query="?search=accessible"), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["count"] == 1

    response_status, response_data = api_get(build_tags_url(query="?search=no-owner"), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["count"] == 0


@pytest.mark.usefixtures("setup_cert_auth_hosts")
def test_cert_auth_get_sap_systems(
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    response_status, response_data = api_get(build_system_profile_sap_system_url(), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["results"][0]["value"] is True
    assert response_data["results"][0]["count"] == 1


@pytest.mark.usefixtures("setup_cert_auth_hosts")
def test_cert_auth_get_sap_sids(
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    response_status, response_data = api_get(build_system_profile_sap_sids_url(), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["results"][0]["value"] == "HBI"
    assert response_data["results"][0]["count"] == 1


@pytest.mark.usefixtures("setup_cert_auth_hosts")
def test_cert_auth_get_operating_system(
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    response_status, response_data = api_get(build_system_profile_operating_system_url(), SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    os_values = [r["value"]["name"] for r in response_data["results"]]
    assert "RHEL" in os_values


def test_cert_auth_get_hosts_in_group(
    setup_cert_auth_hosts: CertAuthHosts,
    api_get: Callable[..., tuple[int, dict]],
    db_create_group: Callable[..., Group],
    db_create_host_group_assoc: Callable[..., None],
) -> None:
    hosts = setup_cert_auth_hosts
    group = db_create_group("cert-auth-group")
    db_create_host_group_assoc(hosts.accessible.id, group.id)
    db_create_host_group_assoc(hosts.no_owner.id, group.id)
    db_create_host_group_assoc(hosts.wrong_owner.id, group.id)

    response_status, response_data = api_get(f"{build_groups_url(group.id)}/hosts", SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(hosts.accessible.id)


# --- Write operations ---


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_cert_auth_patch_host_display_name(
    setup_cert_auth_hosts: CertAuthHosts,
    api_patch: Callable[..., tuple[int, dict]],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    new_name = "updated-display-name"

    response_status, _ = api_patch(
        build_hosts_url(host_list_or_id=hosts.accessible.id),
        {"display_name": new_name},
        identity=SYSTEM_IDENTITY,
    )
    assert_response_status(response_status, 200)

    response_status, response_data = api_get(build_hosts_url(host_list_or_id=hosts.accessible.id), SYSTEM_IDENTITY)
    assert response_data["results"][0]["display_name"] == new_name

    for host in hosts.inaccessible:
        response_status, _ = api_patch(
            build_hosts_url(host_list_or_id=host.id),
            {"display_name": new_name},
            identity=SYSTEM_IDENTITY,
        )
        assert_response_status(response_status, 404)


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_cert_auth_patch_facts(
    setup_cert_auth_hosts: CertAuthHosts,
    api_patch: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    namespace = "ns1"

    response_status, _ = api_patch(
        build_facts_url(hosts.accessible.id, namespace),
        {"new_fact": "new_value"},
        identity=SYSTEM_IDENTITY,
    )
    assert_response_status(response_status, 200)

    for host in hosts.inaccessible:
        response_status, _ = api_patch(
            build_facts_url(host.id, namespace),
            {"new_fact": "new_value"},
            identity=SYSTEM_IDENTITY,
        )
        assert_response_status(response_status, 404)


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_cert_auth_put_facts(
    setup_cert_auth_hosts: CertAuthHosts,
    api_put: Callable[..., tuple[int, dict]],
) -> None:
    hosts = setup_cert_auth_hosts
    namespace = "ns1"

    response_status, _ = api_put(
        build_facts_url(hosts.accessible.id, namespace),
        {"replaced_fact": "replaced_value"},
        identity=SYSTEM_IDENTITY,
    )
    assert_response_status(response_status, 200)

    for host in hosts.inaccessible:
        response_status, _ = api_put(
            build_facts_url(host.id, namespace),
            {"replaced_fact": "replaced_value"},
            identity=SYSTEM_IDENTITY,
        )
        assert_response_status(response_status, 404)


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_cert_auth_delete_host(
    setup_cert_auth_hosts: CertAuthHosts,
    api_delete_host: Callable[..., tuple[int, dict]],
    api_get: Callable[..., tuple[int, dict]],
    db_get_host: Callable[..., Host | None],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, _ = api_delete_host(hosts.accessible.id, identity=SYSTEM_IDENTITY)
    assert_response_status(response_status, 200)

    response_status, _ = api_get(build_hosts_url(host_list_or_id=hosts.accessible.id), SYSTEM_IDENTITY)
    assert_response_status(response_status, 404)

    for host in hosts.inaccessible:
        response_status, _ = api_delete_host(host.id, identity=SYSTEM_IDENTITY)
        assert_response_status(response_status, 404)

    assert db_get_host(hosts.no_owner.id) is not None
    assert db_get_host(hosts.wrong_owner.id) is not None
    assert db_get_host(hosts.other_org.id, org_id=OTHER_ORG_ID) is not None


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_cert_auth_delete_multiple_hosts(
    setup_cert_auth_hosts: CertAuthHosts,
    api_delete_filtered_hosts: Callable[..., tuple[int, dict]],
    db_get_host: Callable[..., Host | None],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_delete_filtered_hosts(
        query_parameters={"display_name": SHARED_DISPLAY_NAME},
        identity=SYSTEM_IDENTITY,
    )
    assert_response_status(response_status, 202)
    assert response_data["hosts_deleted"] == 1

    assert db_get_host(hosts.accessible.id) is None
    assert db_get_host(hosts.no_owner.id) is not None
    assert db_get_host(hosts.wrong_owner.id) is not None
    assert db_get_host(hosts.other_org.id, org_id=OTHER_ORG_ID) is not None


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_cert_auth_delete_all_hosts(
    setup_cert_auth_hosts: CertAuthHosts,
    api_delete_all_hosts: Callable[..., tuple[int, dict]],
    db_get_host: Callable[..., Host | None],
) -> None:
    hosts = setup_cert_auth_hosts
    response_status, response_data = api_delete_all_hosts(
        {"confirm_delete_all": True},
        identity=SYSTEM_IDENTITY,
    )
    assert_response_status(response_status, 202)
    assert response_data["hosts_deleted"] == 1

    assert db_get_host(hosts.accessible.id) is None
    assert db_get_host(hosts.no_owner.id) is not None
    assert db_get_host(hosts.wrong_owner.id) is not None
    assert db_get_host(hosts.other_org.id, org_id=OTHER_ORG_ID) is not None
