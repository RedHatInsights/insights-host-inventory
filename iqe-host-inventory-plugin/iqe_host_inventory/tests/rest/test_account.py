import logging
from copy import deepcopy

import pytest
from iqe.base.auth import AuthType
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.datagen_utils import generate_digits
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_facts
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.kafka_utils import create_or_update_message_expected_fields
from iqe_host_inventory.utils.kafka_utils import delete_message_expected_fields
from iqe_host_inventory.utils.kafka_utils import events_message_expected_headers
from iqe_host_inventory.utils.kafka_utils import prepare_identity_metadata
from iqe_host_inventory.utils.upload_utils import get_archive_and_collect_method

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.fixture()
def no_account_identity(user_identity_correct):
    identity = deepcopy(user_identity_correct)
    identity["identity"].pop("account_number", None)
    return identity


@pytest.fixture()
def account_identity_same(user_identity_correct):
    identity = deepcopy(user_identity_correct)
    identity["identity"]["account_number"] = identity["identity"]["org_id"]
    return identity


@pytest.fixture()
def account_identity_different(user_identity_correct):
    identity = deepcopy(user_identity_correct)
    identity["identity"]["account_number"] = generate_digits(8)
    return identity


@pytest.fixture(scope="session")
def host_inventory_no_account(application, hbi_identity_auth_user, hbi_default_org_id):
    user = deepcopy(hbi_identity_auth_user)
    user.identity.org_id = hbi_default_org_id
    del user.identity.account_number
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture(scope="session")
def host_inventory_account_same(application, hbi_identity_auth_user, hbi_default_org_id):
    user = deepcopy(hbi_identity_auth_user)
    user.identity.org_id = hbi_default_org_id
    user.identity.account_number = hbi_default_org_id
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture(scope="session")
def host_inventory_account_different(application, hbi_identity_auth_user, hbi_default_org_id):
    user = deepcopy(hbi_identity_auth_user)
    user.identity.org_id = hbi_default_org_id
    user.identity.account_number = generate_digits(8)
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "identity",
    [
        lf("no_account_identity"),
        lf("account_identity_same"),
        lf("account_identity_different"),
    ],
)
def test_account_create_not_provided(host_inventory: ApplicationHostInventory, identity: dict):
    """
    Test creating host without providing account number

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test creating host without providing account number
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    host_data.pop("account", None)

    host = host_inventory.kafka.create_host(metadata=metadata, host_data=host_data)
    assert host.account is None
    assert host.org_id == host_data["org_id"]

    response_host = host_inventory.apis.hosts.get_hosts_response(
        insights_id=host_data["insights_id"]
    ).results[0]
    assert response_host.account is None
    assert response_host.org_id == host_data["org_id"]

    response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id).results[0]
    assert response_host.account is None
    assert response_host.org_id == host_data["org_id"]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "identity",
    [
        lf("no_account_identity"),
        lf("account_identity_same"),
        lf("account_identity_different"),
    ],
)
def test_account_create_same_as_org_id(host_inventory: ApplicationHostInventory, identity: dict):
    """
    Test creating host with the same account_number as org_id

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test creating host with the same account_number as org_id
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    host_data["account"] = host_data["org_id"]

    host = host_inventory.kafka.create_host(metadata=metadata, host_data=host_data)
    assert host.account == host_data["account"]
    assert host.org_id == host_data["org_id"]

    response_host = host_inventory.apis.hosts.get_hosts_response(
        insights_id=host_data["insights_id"]
    ).results[0]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]

    response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id).results[0]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "identity",
    [
        lf("no_account_identity"),
        lf("account_identity_same"),
        lf("account_identity_different"),
    ],
)
def test_account_create_different_than_org_id(
    host_inventory: ApplicationHostInventory, identity: dict
):
    """
    Test creating host with different account_number than org_id

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test creating host with different account_number than org_id
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    host_data["account"] = generate_digits(8)

    host = host_inventory.kafka.create_host(metadata=metadata, host_data=host_data)
    assert host.account == host_data["account"]
    assert host.org_id == host_data["org_id"]

    response_host = host_inventory.apis.hosts.get_hosts_response(
        insights_id=host_data["insights_id"]
    ).results[0]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]

    response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id).results[0]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "identity",
    [
        lf("no_account_identity"),
        lf("account_identity_same"),
        lf("account_identity_different"),
    ],
)
def test_account_update_same_account_number(
    host_inventory: ApplicationHostInventory, identity: dict
):
    """
    Test updating account_number on host with the same account_number as org_id

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test updating account_number on host with the same account_number as org_id
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    host_data["account"] = host_data["org_id"]
    host = host_inventory.kafka.create_host(host_data=host_data)

    updated_host_data = deepcopy(host_data)
    updated_host_data["account"] = generate_digits(8)
    updated_host = host_inventory.kafka.create_host(metadata=metadata, host_data=updated_host_data)
    assert host.id == updated_host.id
    # We can't update account_number
    # assert updated_host.account == updated_host_data["account"]
    assert updated_host.account == host_data["account"]
    assert updated_host.org_id == host_data["org_id"]
    # host_inventory.apis.hosts.wait_for_updated(updated_host, account=updated_host_data["account"])  # noqa: E501
    host_inventory.apis.hosts.verify_not_updated(updated_host, account=host_data["account"])

    response_host = host_inventory.apis.hosts.get_hosts_response(
        insights_id=host_data["insights_id"]
    ).results[0]
    # We can't update account_number
    # assert response_host.account == updated_host_data["account"]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]

    response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id).results[0]
    # We can't update account_number
    # assert response_host.account == updated_host_data["account"]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "identity",
    [
        lf("no_account_identity"),
        lf("account_identity_same"),
        lf("account_identity_different"),
    ],
)
def test_account_update_different_account_number(
    host_inventory: ApplicationHostInventory, identity: dict
):
    """
    Test updating account_number on host with different account_number than org_id

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test updating account_number on host with different account_number than org_id
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    host_data["account"] = generate_digits(8)
    host = host_inventory.kafka.create_host(host_data=host_data)

    updated_host_data = deepcopy(host_data)
    updated_host_data["account"] = generate_digits(8)
    updated_host = host_inventory.kafka.create_host(metadata=metadata, host_data=updated_host_data)
    assert host.id == updated_host.id
    # We can't update account_number
    # assert updated_host.account == updated_host_data["account"]
    assert updated_host.account == host_data["account"]
    assert updated_host.org_id == host_data["org_id"]
    # host_inventory.apis.hosts.wait_for_updated(updated_host, account=updated_host_data["account"])  # noqa: E501
    host_inventory.apis.hosts.verify_not_updated(updated_host, account=host_data["account"])

    response_host = host_inventory.apis.hosts.get_hosts_response(
        insights_id=host_data["insights_id"]
    ).results[0]
    # We can't update account_number
    # assert response_host.account == updated_host_data["account"]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]

    response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id).results[0]
    # We can't update account_number
    # assert response_host.account == updated_host_data["account"]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "identity",
    [
        lf("no_account_identity"),
        lf("account_identity_same"),
        lf("account_identity_different"),
    ],
)
@pytest.mark.parametrize("account_type", ["org_id", "random"])
def test_account_update_host(
    host_inventory: ApplicationHostInventory, identity: dict, account_type: str
):
    """
    Test updating host fields on host with account

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test updating host fields on host with account
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    if account_type == "org_id":
        host_data["account"] = host_data["org_id"]
    else:
        host_data["account"] = generate_digits(8)
    host = host_inventory.kafka.create_host(host_data=host_data)

    updated_host_data = deepcopy(host_data)
    updated_host_data["display_name"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(metadata=metadata, host_data=updated_host_data)
    assert host.id == updated_host.id
    assert updated_host.account == host_data["account"]
    assert updated_host.org_id == host_data["org_id"]
    assert updated_host.display_name == updated_host_data["display_name"]
    host_inventory.apis.hosts.wait_for_updated(
        updated_host, display_name=updated_host_data["display_name"]
    )

    response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id).results[0]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]
    assert response_host.display_name == updated_host_data["display_name"]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "identity",
    [
        lf("no_account_identity"),
        lf("account_identity_same"),
        lf("account_identity_different"),
    ],
)
@pytest.mark.parametrize("account_type", ["org_id", "random"])
def test_account_update_host_without_providing_account(
    host_inventory: ApplicationHostInventory, identity: dict, account_type: str
):
    """
    Test updating host fields on host with account without providing account in update message

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test updating host fields on host with account without providing account on update
    """
    metadata = prepare_identity_metadata(identity)
    host_data = host_inventory.datagen.create_host_data()
    if account_type == "org_id":
        host_data["account"] = host_data["org_id"]
    else:
        host_data["account"] = generate_digits(8)
    host = host_inventory.kafka.create_host(host_data=host_data)

    updated_host_data = deepcopy(host_data)
    updated_host_data.pop("account")
    updated_host_data["display_name"] = generate_display_name()
    updated_host = host_inventory.kafka.create_host(metadata=metadata, host_data=updated_host_data)
    assert host.id == updated_host.id
    assert updated_host.account == host_data["account"]
    assert updated_host.org_id == host_data["org_id"]
    assert updated_host.display_name == updated_host_data["display_name"]
    host_inventory.apis.hosts.wait_for_updated(
        updated_host, display_name=updated_host_data["display_name"]
    )

    response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host.id).results[0]
    assert response_host.account == host_data["account"]
    assert response_host.org_id == host_data["org_id"]
    assert response_host.display_name == updated_host_data["display_name"]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_get_host_list(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    account_provided: bool,
):
    """
    Test GET /hosts with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test GET /hosts with various account data in identity
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    response = hbi_test_app.apis.hosts.get_hosts_response(insights_id=host.insights_id)
    assert response.results[0].id == host.id
    assert response.results[0].account == host_data.get("account")


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_get_host_by_id(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    account_provided: bool,
):
    """
    Test GET /hosts/<host_id_list> with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test GET /hosts/<host_id_list> with various account data in identity
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    response = hbi_test_app.apis.hosts.get_hosts_by_id_response(host.id)
    assert response.results[0].id == host.id
    assert response.results[0].account == host_data.get("account")


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_get_host_system_profile(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    account_provided: bool,
):
    """
    Test GET /hosts/<host_id_list>/system_profile with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test GET /hosts/<host_id_list>/system_profile with various account data in identity
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    response = hbi_test_app.apis.hosts.get_hosts_system_profile_response(host.id)
    assert response.results[0].id == host.id


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_get_host_tags(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    account_provided: bool,
):
    """
    Test GET /hosts/<host_id_list>/tags with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test GET /hosts/<host_id_list>/tags with various account data in identity
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    response = hbi_test_app.apis.hosts.get_host_tags_response(host.id)
    assert response.total == 1
    assert len(response.results[host.id]) == len(host_data["tags"])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_get_host_tags_count(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    account_provided: bool,
):
    """
    Test GET /hosts/<host_id_list>/tags/count with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test GET /hosts/<host_id_list>/tags/count with various account data in identity
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    response = hbi_test_app.apis.hosts.get_host_tags_count_response(host.id)
    assert response.total == 1
    assert response.results[host.id] == len(host_data["tags"])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_patch_ansible_name(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    account_provided: bool,
):
    """
    Test PATCH /hosts/<host_id_list> with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test PATCH /hosts/<host_id_list> with various account data in identity
    """
    host_data = host_inventory.datagen.create_host_data()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    new_ansible_host = generate_display_name()
    hbi_test_app.apis.hosts.patch_hosts(host.id, ansible_host=new_ansible_host)
    host_inventory.apis.hosts.wait_for_updated(host, ansible_host=new_ansible_host)

    consumed_host_message = host_inventory.kafka.wait_for_filtered_host_message(
        HostWrapper.id, host.id
    )
    logger.info(f"Consumed message: {consumed_host_message.value}")

    assert consumed_host_message
    assert consumed_host_message.key == host.id
    assert all(
        field in set(consumed_host_message.value.keys())
        for field in create_or_update_message_expected_fields()
    )

    assert consumed_host_message.host.data().get("account") == host_data.get("account")
    assert consumed_host_message.host.ansible_host == new_ansible_host
    assert consumed_host_message.value.get("type") == "updated"

    assert all(
        header in set(consumed_host_message.headers.keys())
        for header in events_message_expected_headers()
    )
    assert consumed_host_message.headers.get("event_type") == "updated"
    assert consumed_host_message.headers.get("insights_id") == host.insights_id


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_patch_facts(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    account_provided: bool,
) -> None:
    """
    Test PATCH /hosts/<host_id_list>/facts/<namespace> with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test PATCH /hosts/<host_id_list>/facts/<namespace> with various account in identity
    """
    host_data = host_inventory.datagen.create_host_data()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    fact_namespace = "some-fancy-facts"
    original_facts = {
        "fact1": generate_uuid(),
        "fact2": generate_uuid(),
    }
    host_data["facts"] = [{"namespace": fact_namespace, "facts": original_facts}]
    host = host_inventory.kafka.create_host(host_data=host_data)

    fact_patch = {"fact2": generate_uuid()}
    hbi_test_app.apis.hosts.merge_facts(host, fact_namespace, fact_patch)
    new_facts = {**original_facts, **fact_patch}  # fact2 will be overriden
    host_message = host_inventory.kafka.wait_for_filtered_host_message(HostWrapper.id, host.id)

    logger.info(f"Consumed message: {host_message.value}")

    assert host_message.key == host.id
    assert all(
        field in set(host_message.value.keys())
        for field in create_or_update_message_expected_fields()
    )

    assert host_message.host.data().get("account") == host_data.get("account")
    assert host_message.host.facts[0]["facts"] == new_facts
    assert host_message.value.get("type") == "updated"

    assert all(
        header in set(host_message.headers.keys()) for header in events_message_expected_headers()
    )
    assert host_message.headers.get("event_type") == "updated"
    assert host_message.headers.get("insights_id") == host.insights_id

    host_inventory.apis.hosts.wait_for_facts_replaced(host, fact_namespace, new_facts)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_put(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    account_provided: bool,
):
    """
    Test PUT /hosts/<host_id_list>/facts/<namespace> with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test PUT /hosts/<host_id_list>/facts/<namespace> with various account in identity
    """
    host_data = host_inventory.datagen.create_host_data()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    fancy_facts = generate_facts()
    host_data["facts"] = fancy_facts
    host = host_inventory.kafka.create_host(host_data=host_data)

    fact_namespace = fancy_facts[0]["namespace"]
    new_facts = {"fact2": generate_uuid()}
    hbi_test_app.apis.hosts.replace_facts(host.id, namespace=fact_namespace, facts=new_facts)

    consumed_host_message = host_inventory.kafka.wait_for_filtered_host_message(
        HostWrapper.id, host.id
    )
    logger.info(f"Consumed message: {consumed_host_message.value}")

    assert consumed_host_message
    assert consumed_host_message.key == host.id
    assert all(
        field in set(consumed_host_message.value.keys())
        for field in create_or_update_message_expected_fields()
    )

    assert consumed_host_message.host.data().get("account") == host_data.get("account")
    assert consumed_host_message.host.facts[0]["facts"] == new_facts
    assert consumed_host_message.value.get("type") == "updated"

    assert all(
        header in set(consumed_host_message.headers.keys())
        for header in events_message_expected_headers()
    )
    assert consumed_host_message.headers.get("event_type") == "updated"
    assert consumed_host_message.headers.get("insights_id") == host.insights_id

    host_inventory.apis.hosts.wait_for_facts_replaced(host, fact_namespace, new_facts)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "hbi_test_app",
    [
        lf("host_inventory_no_account"),
        lf("host_inventory_account_same"),
        lf("host_inventory_account_different"),
    ],
)
@pytest.mark.parametrize("del_method", ["by_id", "bulk"])
@pytest.mark.parametrize("account_provided", [True, False])
def test_account_delete(
    host_inventory: ApplicationHostInventory,
    hbi_test_app: ApplicationHostInventory,
    del_method: str,
    account_provided: bool,
) -> None:
    """
    Test DELETE with various account data in identity

    JIRA: https://issues.redhat.com/browse/ESSNTL-2745

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test DELETE with various account data in identity
    """
    host_data = host_inventory.datagen.create_host_data()
    if account_provided:
        host_data["account"] = generate_digits(8)
    else:
        host_data.pop("account", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    if del_method == "by_id":
        hbi_test_app.apis.hosts.delete_by_id_raw(host.id)
    else:
        hbi_test_app.apis.hosts.delete_filtered(insights_id=host.insights_id)

    consumed_host_message = host_inventory.kafka.wait_for_filtered_host_message(
        HostWrapper.id, host.id
    )
    logger.info(f"Consumed message: {consumed_host_message.value}")

    assert set(consumed_host_message.value) == delete_message_expected_fields()
    consumed_host = consumed_host_message.host
    assert consumed_host.id == host.id
    assert consumed_host.org_id == host.org_id
    assert consumed_host.account == host.account
    assert consumed_host_message.type == "delete"
    assert set(consumed_host_message.headers) == events_message_expected_headers()

    assert consumed_host_message.headers["event_type"] == "delete"
    assert consumed_host_message._raw_message is not None
    value = consumed_host_message.value
    assert value.get("id") == host.id
    assert value.get("org_id") == host_data.get("org_id")
    assert value.get("account") == host_data.get("account")
    assert value.get("type") == "delete"
    assert all(
        header in set(consumed_host_message.headers.keys())
        for header in events_message_expected_headers()
    )
    assert consumed_host_message.headers.get("event_type") == "delete"

    host_inventory.apis.hosts.wait_for_deleted(host)


@pytest.mark.parametrize("operating_system", ["RHEL", "CentOS Linux"])
def test_account_upload_creates_org_id(
    host_inventory: ApplicationHostInventory, hbi_default_org_id: str, operating_system: str
):
    """
    Test creating host via archive upload to ingress/puptoo assigns org_id to host

    JIRA: https://issues.redhat.com/browse/ESSNTL-2870

    metadata:
        requirements: inv-account-integrity
        assignee: fstavela
        importance: critical
        title: Test creating host via archive upload to ingress/puptoo assigns org_id to host
    """
    base_archive, core_collect = get_archive_and_collect_method(operating_system)
    host = host_inventory.upload.create_host(base_archive=base_archive, core_collect=core_collect)
    assert host.org_id == hbi_default_org_id
