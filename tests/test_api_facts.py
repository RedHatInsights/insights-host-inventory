import pytest

from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_facts_url
from tests.helpers.api_utils import build_host_id_list_for_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import get_id_list_from_hosts
from tests.helpers.api_utils import WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.db_utils import DB_FACTS
from tests.helpers.db_utils import DB_FACTS_NAMESPACE
from tests.helpers.db_utils import DB_NEW_FACTS
from tests.helpers.db_utils import get_expected_facts_after_update
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_staleness_timestamps
from tests.helpers.test_utils import SYSTEM_IDENTITY


def test_replace_facts_to_multiple_hosts_with_branch_id(db_create_multiple_hosts, db_get_hosts, api_put):
    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE, query="?branch_id=1234")

    response_status, response_data = api_put(facts_url, DB_NEW_FACTS)
    assert_response_status(response_status, expected_status=200)

    expected_facts = get_expected_facts_after_update("replace", DB_FACTS_NAMESPACE, DB_FACTS, DB_NEW_FACTS)

    for host in db_get_hosts(host_id_list):
        assert host.facts == expected_facts


def test_replace_facts_to_multiple_hosts_including_nonexistent_host(db_create_multiple_hosts, db_get_hosts, api_put):
    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    url_host_id_list = f"{build_host_id_list_for_url(created_hosts)},{generate_uuid()},{generate_uuid()}"
    facts_url = build_facts_url(host_list_or_id=url_host_id_list, namespace=DB_FACTS_NAMESPACE)

    response_status, response_data = api_put(facts_url, DB_NEW_FACTS)

    assert_response_status(response_status, expected_status=400)


def test_replace_facts_to_multiple_hosts_with_empty_key_value_pair(db_create_multiple_hosts, db_get_hosts, api_put):
    new_facts = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE)

    # Set the value in the namespace to an empty fact set
    response_status, response_data = api_put(facts_url, new_facts)
    assert_response_status(response_status, expected_status=200)

    expected_facts = get_expected_facts_after_update("replace", DB_FACTS_NAMESPACE, DB_FACTS, new_facts)

    assert all(host.facts == expected_facts for host in db_get_hosts(host_id_list))


def test_replace_facts_to_namespace_that_does_not_exist(db_create_multiple_hosts, api_patch):
    new_facts = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace="imanonexistentnamespace")

    response_status, response_data = api_patch(facts_url, new_facts)
    assert_response_status(response_status, expected_status=400)


def test_replace_facts_without_fact_dict(api_put):
    facts_url = build_facts_url(1, DB_FACTS_NAMESPACE)
    response_status, response_data = api_put(facts_url, None)

    assert_error_response(response_data, expected_status=400, expected_detail="Request body is not valid JSON")


def test_replace_facts_on_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_put):
    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE)

    response_status, response_data = api_put(facts_url, DB_NEW_FACTS)
    assert_response_status(response_status, expected_status=200)

    expected_facts = get_expected_facts_after_update("replace", DB_FACTS_NAMESPACE, DB_FACTS, DB_NEW_FACTS)

    assert all(host.facts == expected_facts for host in db_get_hosts(host_id_list))


def test_replace_empty_facts_on_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_put):
    new_facts = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE)

    response_status, response_data = api_put(facts_url, new_facts)
    assert_response_status(response_status, expected_status=200)

    expected_facts = get_expected_facts_after_update("replace", DB_FACTS_NAMESPACE, DB_FACTS, new_facts)

    assert all(host.facts == expected_facts for host in db_get_hosts(host_id_list))

    response_status, response_data = api_put(facts_url, DB_NEW_FACTS)
    assert_response_status(response_status, expected_status=200)

    expected_facts = get_expected_facts_after_update("replace", DB_FACTS_NAMESPACE, DB_FACTS, DB_NEW_FACTS)

    assert all(host.facts == expected_facts for host in db_get_hosts(host_id_list))


@pytest.mark.system_culling
def test_replace_facts_on_multiple_culled_hosts(db_create_multiple_hosts, db_get_hosts, api_put):
    staleness_timestamps = get_staleness_timestamps()

    created_hosts = db_create_multiple_hosts(
        how_many=2, extra_data={"facts": DB_FACTS, "stale_timestamp": staleness_timestamps["culled"]}
    )

    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE)

    # Try to replace the facts on a host that has been marked as culled
    response_status, response_data = api_put(facts_url, DB_NEW_FACTS)

    assert_response_status(response_status, expected_status=400)


def test_put_facts_with_RBAC_allowed(subtests, mocker, api_put, db_create_host, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        host = db_create_host(extra_data={"facts": DB_FACTS})
        url = build_facts_url(host_list_or_id=host.id, namespace=DB_FACTS_NAMESPACE)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, response_data = api_put(url, DB_NEW_FACTS)

            assert_response_status(response_status, 200)


def test_put_facts_with_RBAC_denied(subtests, mocker, api_put, db_create_host, db_get_host, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    updated_facts = {"updatedfact1": "updatedvalue1", "updatedfact2": "updatedvalue2"}

    for response_file in WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        host = db_create_host(extra_data={"facts": DB_FACTS})
        url = build_facts_url(host_list_or_id=host.id, namespace=DB_FACTS_NAMESPACE)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, response_data = api_put(url, updated_facts)

            assert_response_status(response_status, 403)

            assert db_get_host(host.id).facts[DB_FACTS_NAMESPACE] != updated_facts


def test_put_facts_with_RBAC_bypassed_as_system(api_put, db_create_host, enable_rbac):
    host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={"facts": DB_FACTS, "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"].get("cn")}},
    )

    url = build_facts_url(host_list_or_id=host.id, namespace=DB_FACTS_NAMESPACE)

    response_status, response_data = api_put(url, DB_NEW_FACTS, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)
