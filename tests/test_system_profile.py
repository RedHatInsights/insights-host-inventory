import pytest

from app.config import Config
from app.environment import RuntimeEnvironment
from app.exceptions import ValidationException
from lib.host_repository import find_hosts_by_staleness
from lib.system_profile_validate import validate_sp_for_branch
from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_system_profile_sap_sids_url
from tests.helpers.api_utils import build_system_profile_sap_system_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import SYSTEM_PROFILE_URL
from tests.helpers.graphql_utils import xjoin_host_response
from tests.helpers.graphql_utils import XJOIN_INVALID_SYSTEM_PROFILE
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SIDS
from tests.helpers.graphql_utils import XJOIN_SYSTEM_PROFILE_SAP_SYSTEM
from tests.helpers.mq_utils import create_kafka_consumer_mock
from tests.helpers.system_profile_utils import system_profile_specification
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import valid_system_profile


OWNER_ID = SYSTEM_IDENTITY["system"]["cn"]


# system_profile tests
def test_system_profile_includes_owner_id(api_get, patch_xjoin_post):
    host_id = generate_uuid()
    response = xjoin_host_response("2021-02-10T08:07:03Z")
    response["hosts"]["data"][0]["id"] = host_id
    patch_xjoin_post({"data": response})

    url = build_system_profile_url(host_list_or_id=host_id)

    response_status, response_data = api_get(url)

    assert "owner_id" in response_data["results"][0]["system_profile"]
    assert response_status == 200


@pytest.mark.parametrize(
    "boot_time",
    [
        "clearly wrong",
        pytest.param("", id="empty str also wrong"),
        "12:25 Mar 19, 2019",
        "2021-05-11T19:46:56Z+00:00",
        "2021-05-11T19:46:56.951+00:00Z",
        "2021-05-11-12T19:46",
        "2021-05T19:46.951",
    ],
)
def test_system_profile_invalid_date_format(mq_create_or_update_host, boot_time):
    system_profile = valid_system_profile()
    system_profile["owner_id"] = OWNER_ID
    system_profile["last_boot_time"] = boot_time
    host = minimal_host(system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)


@pytest.mark.parametrize(
    "boot_time",
    [
        "2021-05-11T19:46:56Z",
        "2021-05-11T19:46:56+00:00",
        "2021-05-11T19:46:56.951Z",
        "2021-05-11T19:46:56.951+00:00",
        "2021-05-11T19:46:56",
        "2021-05-11T19:46:56.951",
    ],
)
def test_system_profile_valid_date_format(mq_create_or_update_host, boot_time):
    system_profile = valid_system_profile()
    system_profile["owner_id"] = OWNER_ID
    system_profile["last_boot_time"] = boot_time
    host = minimal_host(system_profile=system_profile)

    mq_create_or_update_host(host)


# sap endpoint tests
def test_system_profile_sap_system_endpoint_response(
    mocker, graphql_system_profile_sap_system_query_with_response, api_get
):
    url = build_system_profile_sap_system_url()

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == XJOIN_SYSTEM_PROFILE_SAP_SYSTEM["hostSystemProfile"]["sap_system"]["data"]
    assert (
        response_data["total"] == XJOIN_SYSTEM_PROFILE_SAP_SYSTEM["hostSystemProfile"]["sap_system"]["meta"]["total"]
    )
    assert (
        response_data["count"] == XJOIN_SYSTEM_PROFILE_SAP_SYSTEM["hostSystemProfile"]["sap_system"]["meta"]["count"]
    )


def test_system_profile_sap_sids_endpoint_response(
    mocker, graphql_system_profile_sap_sids_query_with_response, api_get
):
    url = build_system_profile_sap_sids_url()

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == XJOIN_SYSTEM_PROFILE_SAP_SIDS["hostSystemProfile"]["sap_sids"]["data"]
    assert response_data["total"] == XJOIN_SYSTEM_PROFILE_SAP_SIDS["hostSystemProfile"]["sap_sids"]["meta"]["total"]
    assert response_data["count"] == XJOIN_SYSTEM_PROFILE_SAP_SIDS["hostSystemProfile"]["sap_sids"]["meta"]["count"]


def test_get_system_profile_sap_system_with_RBAC_allowed(
    subtests, mocker, graphql_system_profile_sap_system_query_with_response, api_get, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    url = build_system_profile_sap_system_url()

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)


def test_get_system_profile_sap_sids_with_RBAC_allowed(
    subtests, mocker, graphql_system_profile_sap_sids_query_with_response, api_get, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    url = build_system_profile_sap_sids_url()

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)


def test_get_system_profile_with_RBAC_denied(subtests, mocker, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    urls = (build_system_profile_sap_system_url(), build_system_profile_sap_sids_url())

    for url in urls:
        for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
            mock_rbac_response = create_mock_rbac_response(response_file)
            with subtests.test():
                get_rbac_permissions_mock.return_value = mock_rbac_response

                response_status, response_data = api_get(url)

                assert_response_status(response_status, 403)


def test_get_system_profile_sap_system_with_RBAC_bypassed_as_system(
    graphql_system_profile_sap_system_query_with_response, api_get, enable_rbac
):
    url = build_system_profile_sap_system_url()

    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


def test_get_system_profile_sap_sids_with_RBAC_bypassed_as_system(
    graphql_system_profile_sap_sids_query_with_response, api_get, enable_rbac
):
    url = build_system_profile_sap_sids_url()

    response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


def test_get_system_profile_RBAC_allowed(mocker, subtests, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    host_id = generate_uuid()

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            response_status, response_data = api_get(f"{HOST_URL}/{host_id}/system_profile")

            assert_response_status(response_status, 200)


def test_get_system_profile_RBAC_denied(mocker, subtests, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    find_hosts_by_staleness_mock = mocker.patch(
        "lib.host_repository.find_hosts_by_staleness", wraps=find_hosts_by_staleness
    )

    host_id = generate_uuid()

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            response_status, response_data = api_get(f"{HOST_URL}/{host_id}/system_profile")

            assert_response_status(response_status, 403)
            find_hosts_by_staleness_mock.assert_not_called()


def test_get_host_with_invalid_system_profile(api_get, patch_xjoin_post):
    # patch xjoin post to respond with graphql_utils.XJOIN_INVALID_SYSTEM_PROFILE
    patch_xjoin_post(XJOIN_INVALID_SYSTEM_PROFILE)
    url = build_system_profile_url(host_list_or_id=generate_uuid())
    response_status, _ = api_get(url)

    assert_response_status(response_status, 500)


def test_get_system_profile_of_host_that_does_not_exist(api_get):
    expected_count = 0
    expected_total = 0
    host_id = generate_uuid()

    response_status, response_data = api_get(f"{HOST_URL}/{host_id}/system_profile")

    assert_response_status(response_status, 200)

    assert response_data["count"] == expected_count
    assert response_data["total"] == expected_total


@pytest.mark.parametrize("invalid_host_id", ["notauuid", "922680d3-4aa2-4f0e-9f39-38ab8ea318bb,notuuid"])
def test_get_system_profile_with_invalid_host_id(api_get, invalid_host_id):
    response_status, response_data = api_get(f"{HOST_URL}/{invalid_host_id}/system_profile")

    assert_error_response(response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("partitions", [1, 5])
@pytest.mark.parametrize("messages_per_partition_per_poll", [1, 10])
@pytest.mark.parametrize("number_of_polls", [1, 3])
def test_validate_sp_for_branch(mocker, partitions, messages_per_partition_per_poll, number_of_polls):
    # Mock schema fetch
    get_schema_from_url_mock = mocker.patch("lib.system_profile_validate.get_schema_from_url")
    get_schema_from_url_mock.return_value = system_profile_specification()
    config = Config(RuntimeEnvironment.SERVICE)
    fake_consumer = create_kafka_consumer_mock(
        mocker, config.host_ingress_topic, partitions, messages_per_partition_per_poll, number_of_polls
    )
    max_messages_to_poll = 50

    # Due to the parameterization, each call to poll() can return 1-50 messages.
    # number_of_polls is also parameterized, meaning that this simulates a total of
    # 1-150 messages. Setting max_messages to 50 allows this test to validate
    # both loop conditions in get_hosts_from_kafka_messages().

    validation_results = validate_sp_for_branch(
        fake_consumer,
        topics=[config.host_ingress_topic],
        repo_fork="test_repo",
        repo_branch="test_branch",
        days=3,
        max_messages=max_messages_to_poll,
    )

    assert "test_repo/test_branch" in validation_results

    pass_count = 0
    for reporter in validation_results["test_repo/test_branch"]:
        pass_count += validation_results["test_repo/test_branch"][reporter].pass_count

    assert pass_count == min(partitions * messages_per_partition_per_poll * number_of_polls, max_messages_to_poll)


def test_validate_sp_no_data(mocker):
    config = Config(RuntimeEnvironment.SERVICE)
    fake_consumer = create_kafka_consumer_mock(mocker, config.host_ingress_topic, 1, 0)
    get_schema_from_url_mock = mocker.patch("lib.system_profile_validate.get_schema_from_url")
    get_schema_from_url_mock.return_value = system_profile_specification()

    with pytest.raises(expected_exception=ValueError) as excinfo:
        validate_sp_for_branch(
            fake_consumer,
            topics=[config.host_ingress_topic],
            repo_fork="foo",
            repo_branch="bar",
            days=3,
            max_messages=10,
        )
    assert "No data available at the provided date." in str(excinfo.value)


def test_validate_sp_for_missing_branch_or_repo(mocker):
    # Mock schema fetch
    get_schema_from_url_mock = mocker.patch("lib.system_profile_validate.get_schema_from_url")
    get_schema_from_url_mock.side_effect = ValueError("Schema not found at URL!")
    config = Config(RuntimeEnvironment.SERVICE)
    fake_consumer = create_kafka_consumer_mock(mocker, config.host_ingress_topic, 1, 10)

    with pytest.raises(expected_exception=ValueError) as excinfo:
        validate_sp_for_branch(
            fake_consumer,
            topics=[config.host_ingress_topic],
            repo_fork="foo",
            repo_branch="bar",
            days=3,
            max_messages=10,
        )
    assert "Schema not found at URL" in str(excinfo.value)


def test_validate_sp_for_invalid_days(api_post):
    response_status, response_data = api_post(
        url=f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=0", host_data=None
    )

    assert response_status == 400
