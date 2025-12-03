import logging

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import ErrorNotificationWrapper
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import rand_str
from iqe_host_inventory.utils.tag_utils import convert_tag_from_nested_to_structured
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string
from iqe_host_inventory.utils.tag_utils import normalize_tags
from iqe_host_inventory.utils.tag_utils import sort_tags
from iqe_host_inventory_api import ApiException

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags",
    [
        pytest.param([], id="none"),
        pytest.param(
            [{"namespace": None, "key": rand_str(), "value": rand_str()}], id="no-namespace"
        ),
        pytest.param([{"namespace": rand_str(), "key": rand_str(), "value": None}], id="no-value"),
        pytest.param(
            [{"namespace": None, "key": rand_str(), "value": None}], id="no-namespace-no-value"
        ),
        pytest.param(
            [gen_tag(), gen_tag(), {"namespace": None, "key": rand_str(), "value": rand_str()}],
            id="many-random",
        ),
    ],
)
def test_host_creation_with_tags(
    host_inventory: ApplicationHostInventory, tags: list[dict[str, str | None] | TagDict]
):
    """
    Ensure it's possible to create a host with "tags" field using MQ and those
    tags are present in the host output message on events kafka topic.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-4263

    1. Create a host with "tags" field via MQ
    2. Verify "tags" field is present in host message output with proper value

    metadata:
        requirements: inv-tags, inv-host-create
        assignee: fstavela
        importance: high
        title: create hosts with tags
    """
    host_data = host_inventory.datagen.create_host_data(tags=tags)
    host = host_inventory.kafka.create_host(host_data=host_data)

    expected_tags = sort_tags(tags)
    actual_tags = sort_tags(host.tags)
    assert actual_tags == expected_tags

    response = host_inventory.apis.hosts.get_host_tags_response(host.id)
    actual_tags = sort_tags(response.results[host.id])
    assert actual_tags == expected_tags


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tag",
    [
        pytest.param({"key": "*()%$"}, id="key"),
        pytest.param({"key": "^~&-=", "value": "}{?:><"}, id="key-value"),
        pytest.param({"namespace": ";?:@", "key": "&+$-_,.", "value": "!~*'()#"}, id="all"),
        pytest.param(
            {"namespace": "Ns%21%40%23%24", "key": "k%2Fe%3Dy%5C", "value": "v%3A%7C%5C%7B%5C"},
            id="escaped",
        ),
    ],
)
def test_create_hosts_with_tag_containing_special_characters(
    host_inventory: ApplicationHostInventory, tag: dict[str, str]
):
    """
    Create hosts with tags containing special characters.

    1. Create a host with tag containing special characters via MQ
    2. Make sure hosts were created and corresponding tags are present

    metadata:
        requirements: inv-tags, inv-host-create
        assignee: fstavela
        importance: high
        title: create hosts with tags with special characters
    """
    # Create host and compare MQ event tags
    host_data = host_inventory.datagen.create_host_data(tags=[tag])
    host = host_inventory.kafka.create_host(host_data=host_data)
    assert host.tags == normalize_tags([tag])

    # Get tags via API
    response = host_inventory.apis.hosts.get_host_tags_response(host.id)
    assert response.results
    # do not compare "None" values
    # (server always returns all 3 keys, even if we don't provide them)
    assert [dict_tag.to_dict() for dict_tag in response.results[host.id]] == normalize_tags([tag])

    # Get host by tags
    query_tags = [convert_tag_to_string(tag, True)]
    response = host_inventory.apis.hosts.get_hosts_response(tags=query_tags)
    assert response.results
    assert host.id in {res_host.id for res_host in response.results}


@pytest.mark.ephemeral
def test_tags_with_commas(host_inventory: ApplicationHostInventory):
    """
    Create hosts with tags containing commas and filter by them

    https://issues.redhat.com/browse/ESSNTL-3631

    metadata:
        requirements: inv-tags, inv-host-create
        assignee: fstavela
        importance: medium
        title: Create hosts with tags with commas and filter by them
    """
    tag = gen_tag(value="Sacramento, CA")
    host_data = host_inventory.datagen.create_host_data(tags=[tag])
    host = host_inventory.kafka.create_host(host_data=host_data)
    assert host.tags == [tag]

    str_tag = convert_tag_to_string(tag)
    response = host_inventory.apis.hosts.get_hosts_response(tags=[str_tag])
    assert response.count == 1
    assert response.results[0].id == host.id

    query_tag = convert_tag_to_string(tag, True)
    response = host_inventory.apis.hosts.get_hosts_response(tags=[query_tag])
    assert response.count == 1
    assert response.results[0].id == host.id


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tag",
    [
        pytest.param({"namespace": "mynamespace", "key": "my/key", "value": "myvalue"}, id="key"),
        # pytest.param(
        #     {"namespace": "mynamespace", "key": "mykey", "value": "my/value"}, id="value"
        # ),  # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-17554 is fixed
        # pytest.param(
        #     {"namespace": "mynamespace", "key": "my/key", "value": "my/value"}, id="key-value"
        # ),  # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-17554 is fixed
        # pytest.param(
        #     {"key": "my/key", "value": "myvalue"},
        #     id="empty-namespace",
        # ),  # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-17558 is fixed
        pytest.param(
            {"namespace": "mynamespace", "key": "my/key"},
            id="empty-value",
        ),
        # pytest.param(
        #     {"key": "my/key"},
        #     id="only-key",
        # ),  # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-17558 is fixed
    ],
)
def test_tags_with_slashes(host_inventory: ApplicationHostInventory, tag: dict[str, str]):
    """
    https://issues.redhat.com/browse/RHINENG-17045

    metadata:
        requirements: inv-tags, inv-host-create
        assignee: fstavela
        importance: medium
        title: Create hosts with tags with slashes and filter by them
    """
    host_data = host_inventory.datagen.create_host_data(tags=[tag])
    host = host_inventory.kafka.create_host(host_data=host_data)
    assert host.tags == normalize_tags([tag])

    # Use the exact tags parameter without URL encoding
    str_tag = convert_tag_to_string(tag)
    response = host_inventory.apis.hosts.get_hosts_response(tags=[str_tag])
    assert response.count == 1
    assert response.results[0].id == host.id

    # Encode tags parameter to URL format
    query_tag = convert_tag_to_string(tag, True)
    response = host_inventory.apis.hosts.get_hosts_response(tags=[query_tag])
    assert response.count == 1
    assert response.results[0].id == host.id


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags",
    [
        {},
        {rand_str(): {rand_str(): [rand_str()]}},
        {rand_str(): {rand_str(): [rand_str(), rand_str()]}},
        {
            rand_str(): {
                rand_str(): [rand_str(), rand_str()],
                rand_str(): [rand_str()],
                rand_str(): [],
            }
        },
        {None: {rand_str(): [rand_str()]}},
        {"": {rand_str(): [rand_str()]}},
        {rand_str(): {rand_str(): [""]}},
        {rand_str(): {rand_str(): None}},
    ],
)
def test_host_creation_with_nested_tags(
    host_inventory: ApplicationHostInventory, tags: dict[str | None, dict[str, list[str] | None]]
):
    """
    Ensure it's possible to create a host with "tags" field using the nested
    input format via MQ and those tags are present in the host output message
    on events kafka topic.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5156

    1. Create a host with "tags" field using the nested input format via MQ
    2. Verify "tags" field is present in host output message with proper value

    metadata:
        requirements: inv-tags, inv-host-create
        assignee: fstavela
        importance: high
        title: create hosts with tags in the nested format
    """
    host_data = host_inventory.datagen.create_host_data(tags=tags)
    host = host_inventory.kafka.create_host(host_data=host_data)

    expected_tags = sort_tags(convert_tag_from_nested_to_structured(tags))
    actual_tags = sort_tags(host.tags)
    assert actual_tags == expected_tags


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags,expected_tags,ns_to_remove_tags",
    [
        (
            {"test-ns-1": {rand_str(): [rand_str()]}, "test-ns-2": {"test-key": ["test-value"]}},
            {"test-ns-2": {"test-key": ["test-value"]}},
            "test-ns-1",
        ),
        ({"test-ns-1": {rand_str(): [rand_str()], rand_str(): [rand_str()]}}, {}, "test-ns-1"),
        (
            {None: {rand_str(): [rand_str()]}, "test-ns-2": {"test-key": ["test-value"]}},
            {"test-ns-2": {"test-key": ["test-value"]}},
            None,
        ),
    ],
)
def test_remove_all_tags_from_a_namespace(
    host_inventory: ApplicationHostInventory,
    tags: dict[str | None, dict[str, list[str]]],
    expected_tags: dict[str, dict[str, list[str]]],
    ns_to_remove_tags: str | None,
):
    """
    Ensure it's possible to remove all tags from a host using the nested input
    tag format.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5156

    1. Create a host with "tags" field using the nested input format via MQ
    2. Verify "tags" field is present in host output message with proper value
    3. Update the host tags by removing all "tags" from a specific namespace via MQ
    4. Ensure the "tags" were correctly removed by checking the host output message

    metadata:
        requirements: inv-tags, inv-host-update
        assignee: fstavela
        importance: high
        title: confirm removing all tags of a specific name-space using nested tag input
    """
    host_data = host_inventory.datagen.create_host_data(tags=tags)
    host = host_inventory.kafka.create_host(host_data=host_data)

    expected_tags_before_update = sort_tags(convert_tag_from_nested_to_structured(tags))
    actual_tags_before_update = sort_tags(host.tags)
    assert actual_tags_before_update == expected_tags_before_update

    logger.info("Updating host tags to remove all tags from a specific namespace")
    tags[ns_to_remove_tags] = {}
    host_data["tags"] = tags

    host = host_inventory.kafka.create_host(host_data=host_data)

    expected_tags_after_update = sort_tags(convert_tag_from_nested_to_structured(expected_tags))
    actual_tags_after_update = sort_tags(host.tags)
    assert actual_tags_after_update == expected_tags_after_update


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "create_tags,update_tags,expected_tags",
    [
        (
            {"satellite": {"foo": ["foo", "bar"], "foo1": ["bar"], "foo2": []}},
            {"satellite": {"foo": ["foo-update", "bar"], "foo1": ["bar-update"]}},
            {"satellite": {"foo": ["foo-update", "bar"], "foo1": ["bar-update"]}},
        ),
        (
            {"satellite": {"foo": ["bar"]}, "satellite2": {"foo": ["bar"]}},
            {"satellite": {"foo": ["bar-update"]}, "satellite3": {"foo": ["bar"]}},
            {
                "satellite": {"foo": ["bar-update"]},
                "satellite2": {"foo": ["bar"]},
                "satellite3": {"foo": ["bar"]},
            },
        ),
        (
            {"satellite": {"foo": ["bar"]}, "satellite-2": {"foo": ["bar"]}},
            {"satellite": {"foo": ["foo-update"]}, "satellite-2": {}},
            {"satellite": {"foo": ["foo-update"]}},
        ),
    ],
)
def test_update_host_tags(
    create_tags: dict[str, dict[str, list[str]]],
    update_tags: dict[str, dict[str, list[str]]],
    expected_tags: dict[str, dict[str, list[str]]],
    host_inventory: ApplicationHostInventory,
):
    """
    Ensure it's possible to update host "tags" using the nested input format
    via MQ.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5156

     1. Create a host with "tags" field using the nested input format via MQ
     2. Verify "tags" field is present in the host output with proper value
     3. Update the host "tags" using the nested input format via MQ
     4. Make sure the "tags" were updated and are present in the host output message
        with proper value

     metadata:
        requirements: inv-tags, inv-host-update
        assignee: fstavela
        importance: high
        title: update hosts with tags in the nested format
    """

    host_data = host_inventory.datagen.create_host_data(tags=create_tags)

    host = host_inventory.kafka.create_host(host_data)

    expected_tags_before_update = sort_tags(convert_tag_from_nested_to_structured(create_tags))
    actual_tags_before_update = sort_tags(host.tags)
    assert actual_tags_before_update == expected_tags_before_update

    logger.info("Updating host tags")
    host_data["tags"] = update_tags
    host = host_inventory.kafka.create_host(host_data)

    expected_tags_after_update = sort_tags(convert_tag_from_nested_to_structured(expected_tags))
    actual_tags_after_update = sort_tags(host.tags)
    assert actual_tags_after_update == expected_tags_after_update


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags",
    [
        {rand_str(): {rand_str(min_chars=256, max_chars=500): [rand_str()]}},
        {rand_str(): {rand_str(): rand_str()}},
        {rand_str(min_chars=256, max_chars=500): {rand_str(): [rand_str()]}},
        {rand_str(): {rand_str(): [rand_str(min_chars=256, max_chars=500)]}},
        {rand_str(): {"": [rand_str()]}},
        {rand_str(): [{rand_str(): rand_str()}]},
    ],
)
def test_host_creation_with_invalid_nested_tags(
    host_inventory: ApplicationHostInventory, tags: dict[str, dict[str, list[str]]]
):
    """
    Attempt to create hosts with invalid tags using the nested input format.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5156

    1. Attempt to create hosts with invalid tags using the nested input format via MQ
    2. Make sure hosts were not created

    metadata:
        requirements: inv-tags, inv-mq-host-field-validation
        assignee: fstavela
        importance: medium
        negative: true
        title: confirm host creation fails for invalid nested tags
    """
    logger.info("Attempting to create a host with tags using the new nested input format")
    host_data = host_inventory.datagen.create_host_data(tags=tags)
    host_inventory.kafka.produce_host_create_messages([host_data])
    host_inventory.kafka.wait_for_filtered_error_message(
        ErrorNotificationWrapper.display_name, host_data["display_name"]
    )


@pytest.mark.ephemeral
def test_filter_host_by_tag(host_inventory: ApplicationHostInventory):
    """
    Create a host with tag, filter hosts by tag name.

    1. Create a host with unique tag via MQ
    2. Filter hosts by previously mentioned tag via REST API
    3. Make sure only one host with expected id is found

    metadata:
        requirements: inv-hosts-filter-by-tags
        assignee: fstavela
        importance: high
        title: Inventory: Filter by tag name
    """
    tag = gen_tag()
    host_data = host_inventory.datagen.create_host_data(tags=[tag])
    host = host_inventory.kafka.create_host(host_data)

    tag_str = convert_tag_to_string(tag)

    response_hosts = host_inventory.apis.hosts.get_hosts(tags=[tag_str])

    assert len(response_hosts) == 1
    assert response_hosts[0].id == host.id


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tag",
    [
        pytest.param({"key": rand_str(), "value": rand_str()}, id="random-kv"),
        pytest.param({"namespace": rand_str(), "key": rand_str()}, id="random-ns-k"),
        pytest.param({"namespace": rand_str(), "key": rand_str(), "value": None}, id="value-none"),
        pytest.param({"key": rand_str()}, id="key-only"),
        pytest.param({"namespace": None, "key": rand_str(), "value": None}, id="ns-v-none"),
        pytest.param({"namespace": None, "key": rand_str(), "value": rand_str()}, id="in-none"),
        pytest.param({"key": rand_str(), "value": ""}, id="value-blank"),
        pytest.param({"namespace": "", "key": rand_str()}, id="ns-blank"),
    ],
)
def test_filter_host_by_tag_combinations(
    host_inventory: ApplicationHostInventory, tag: dict[str, str | None]
):
    """
    Create hosts with different valid tags combinations: tag with no namespace
    set, no value set or both, filter hosts by tag name.

    1. Create a host with tag containing no namespace (e.g. "foo=bar") via MQ
    2. Create a host with tag containing no value (e.g. "foo/bar") via MQ
    3. Create a host with tag containing no namespace or value (e.g. "foo") via MQ
    4. Filter hosts by previously mentioned tag via REST API
    5. Make sure only one host with expected id is found

    metadata:
        requirements: inv-hosts-filter-by-tags
        assignee: fstavela
        importance: high
        title: Inventory: Filter by tag name combinations
    """
    host_data = host_inventory.datagen.create_host_data(tags=[tag])
    host = host_inventory.kafka.create_host(host_data)

    tag_str = convert_tag_to_string(tag)

    response_hosts = host_inventory.apis.hosts.get_hosts(tags=[tag_str])

    assert len(response_hosts) == 1
    assert response_hosts[0].id == host.id


@pytest.mark.ephemeral
def test_filter_hosts_by_tag(host_inventory: ApplicationHostInventory):
    """
    Create multiple hosts: one with no tags, one with 1 tag, one with same +
    extra tag. Make sure filtering by different tags works as expected.

    1. Create a host with no tags via MQ
    2. Create a host with 1 tag, e.g. "tag_1" via MQ
    3. Create a host with 2 tags, one of each from the previous step, e.g. "tag_1", "tag_2" via MQ
    4. Filter hosts by "tag_1" via REST API, make sure 2 expected hosts found
    5. Filter hosts by "tag_2" via REST API, make sure only 1 host found

    metadata:
        requirements: inv-hosts-filter-by-tags
        assignee: fstavela
        importance: high
        title: Inventory: Confirm filtering by different tags works as expected
    """
    tag_1 = gen_tag()
    tag_2 = gen_tag()
    host_data2 = host_inventory.datagen.create_host_data(tags=[tag_1])
    host_data3 = host_inventory.datagen.create_host_data(tags=[tag_1, tag_2])

    host_1 = host_inventory.kafka.create_host()
    host_2 = host_inventory.kafka.create_host(host_data2)
    host_3 = host_inventory.kafka.create_host(host_data3)

    str_tag_1 = convert_tag_to_string(tag_1)
    response_hosts = host_inventory.apis.hosts.get_hosts(tags=[str_tag_1])

    assert len(response_hosts) == 2
    assert {host.id for host in response_hosts} == {host_2.id, host_3.id}
    assert host_1.id not in {host.id for host in response_hosts}

    str_tag_2 = convert_tag_to_string(tag_2)
    response_hosts = host_inventory.apis.hosts.get_hosts(tags=[str_tag_2])

    assert len(response_hosts) == 1
    assert response_hosts[0].id == host_3.id


@pytest.mark.ephemeral
def test_filter_hosts_by_tags(host_inventory: ApplicationHostInventory):
    """
    Create multiple hosts: one with 1 tag, one with 2 tags. Make sure
    filtering by multiple tags works as expected.

    1. Create a host with 2 tags, e.g. "tag_1", "tag_2" via MQ
    2. Create a host with 1 tag, e.g. "tag_3" via MQ
    3. Filter hosts by "tag_1" and "tag_2" via REST API, make sure only 1 host found

    metadata:
        requirements: inv-hosts-filter-by-tags
        assignee: fstavela
        importance: high
        title: Inventory: Confirm filtering by multiple tags works as expected
    """
    tag_1 = gen_tag()
    tag_2 = gen_tag()
    tag_3 = gen_tag()

    host_data = host_inventory.datagen.create_host_data(tags=[tag_1, tag_2])
    host_data2 = host_inventory.datagen.create_host_data(tags=[tag_3])
    host = host_inventory.kafka.create_host(host_data)
    host_inventory.kafka.create_host(host_data2)

    str_tag_1 = convert_tag_to_string(tag_1)
    str_tag_2 = convert_tag_to_string(tag_2)

    response_hosts = host_inventory.apis.hosts.get_hosts(tags=[str_tag_1, str_tag_2])

    assert len(response_hosts) == 1
    assert response_hosts[0].id == host.id


@pytest.mark.ephemeral
def test_filter_hosts_by_shared_tags(host_inventory: ApplicationHostInventory):
    """
    Create multiple hosts: two with 1 tag, two with 2 tags. Make sure
    filtering by multiple tags works as expected.

    1. Create a host with 1 tag, e.g. "tag_1" via MQ
    2. Create a host with 2 tags, one of each from the previous step, e.g. "tag_1", "tag_2" via MQ
    3. Create a host with 1 tag, e.g. "tag_3" via MQ
    5. Create a host with 2 tag, one of each from the previous step,  e.g. "tag_2", "tag_3" via MQ
    5. Filter hosts by "tag_1" and "tag_2" via REST API, make sure only 3 hosts found

    metadata:
        requirements: inv-hosts-filter-by-tags
        assignee: zabikeno
        importance: high
        title: Inventory: Confirm filtering by multiple tags works as expected
    """
    tag_1 = gen_tag()
    tag_2 = gen_tag()
    tag_3 = gen_tag()

    hosts_data = [
        host_inventory.datagen.create_host_data(tags=[tag_1]),
        host_inventory.datagen.create_host_data(tags=[tag_1, tag_2]),
        host_inventory.datagen.create_host_data(tags=[tag_3]),
        host_inventory.datagen.create_host_data(tags=[tag_2, tag_3]),
    ]

    host_1, host_2, _, host_3 = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    expected_ids = {host_1.id, host_2.id, host_3.id}

    str_tag_1 = convert_tag_to_string(tag_1)
    str_tag_2 = convert_tag_to_string(tag_2)

    response_hosts = host_inventory.apis.hosts.get_hosts(tags=[str_tag_1, str_tag_2])
    response_ids = {host.id for host in response_hosts}

    assert len(response_hosts) == 3
    assert response_ids & expected_ids == expected_ids


@pytest.mark.parametrize(
    "tag",
    [
        pytest.param(rand_str(min_chars=256, max_chars=500), id="no value"),
        pytest.param(f"{rand_str()}={rand_str(min_chars=256, max_chars=500)}", id="some value"),
        pytest.param(
            f"{rand_str(min_chars=256, max_chars=500)}/{rand_str()}={rand_str()}", id="all"
        ),
        pytest.param("", id="empty"),
        pytest.param(f"{rand_str()}/=", id="missing tag and value"),
        pytest.param(f"{rand_str()}//={rand_str()}", id="slash tag"),
        pytest.param(f"/{rand_str()}=={rand_str()}", id="double equal"),
        pytest.param(f"{rand_str()}/={rand_str()}", id="missing tag"),
        pytest.param(f"{rand_str()}//=={rand_str()}", id="why do we even try"),
    ],
)
def test_filter_hosts_by_invalid_tag(tag, host_inventory: ApplicationHostInventory):
    """
    Attempt to filter hosts by non-existing or invalid tags.

    1. Attempt to filter hosts by non-existing tags
    2. Make sure 0 results were returned
    3. Attempt to filter hosts by invalid tag - empty value, incorrect separator placements, >255
       chars, special characters or non-string value
    4. Make sure 0 results returned and/or error was thrown

    metadata:
        requirements: inv-hosts-filter-by-tags, inv-api-validation
        assignee: fstavela
        importance: low
        negative: true
        title: Inventory: Filter hosts by non-existing or invalid tags
    """
    with pytest.raises(ApiException) as err:
        host_inventory.apis.hosts.get_hosts(tags=[tag])

    assert err.value.status == 400


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags",
    [
        pytest.param([], id="count=0"),
        pytest.param([gen_tag()], id="count=1"),
        pytest.param([gen_tag(), gen_tag(), gen_tag()], id="count=3"),
    ],
)
def test_host_tags_count(host_inventory: ApplicationHostInventory, tags: list[TagDict]):
    """
    Create hosts with 0/1/many tags, make sure tags count reflects actual tags
    count for each of them.

    1. Create a host with no tags via MQ, make sure tag_count call returns 0 results
    2. Create a host with 1 tag via MQ, make sure tag_count call returns 1 result
    3. Create a host with 3 tags via MQ, make sure tag_count call returns 3 results

    metadata:
        requirements: inv-hosts-get-tags-count
        assignee: fstavela
        importance: medium
        title: confirm 0/1/many tags from creation match the resulting facts
    """
    host_data = host_inventory.datagen.create_host_data(tags=tags)
    host = host_inventory.kafka.create_host(host_data)
    response = host_inventory.apis.hosts.get_host_tags_count_response(host.id)
    assert response.results[host.id] == len(tags)


@pytest.mark.ephemeral
def test_hosts_tags_count(host_inventory: ApplicationHostInventory):
    """
    Create hosts with 0/1/many tags, get tags count for all of them in one
    request.

    1. Create a host with no tags via MQ
    2. Create a host with 1 tag via MQ
    3. Create a host with 3 tags via MQ
    4. Make tags count call for all 3 hosts via REST API,
       make sure response contains proper numbers

    metadata:
        requirements: inv-hosts-get-tags-count
        assignee: fstavela
        importance: medium
        title: Confirm that is possible to create hosts with 0/1/many tags
    """
    tags: list[list[TagDict]] = [[], [gen_tag()], [gen_tag(), gen_tag(), gen_tag()]]
    hosts_data = [
        host_inventory.datagen.create_host_data(tags=current_tags) for current_tags in tags
    ]

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    host_ids = [host.id for host in hosts]

    response = host_inventory.apis.hosts.get_host_tags_count_response(host_ids)

    expected_count = {len(current_tags) for current_tags in tags}
    assert set(response.results.values()) == expected_count


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "test_host_inventory",
    [
        pytest.param(
            lf("host_inventory_identity_auth_user"),
            id="user",
        ),
        pytest.param(
            lf("host_inventory_identity_auth_system"),
            id="system",
        ),
    ],
)
def test_post_tags(
    test_host_inventory: ApplicationHostInventory,
    hbi_ephemeral_base_url: str,
    hbi_default_account_number: str,
) -> None:
    """
    Test that "post tags" are operating correctly in ephemeral.

    https://issues.redhat.com/browse/RHINENG-17910

    metadata:
        requirements: inv-post-tags-endpoints
        assignee: addubey
        importance: high
        title: Inventory: Test that "post tags" are operating correctly in ephemeral.
    """
    host_data = test_host_inventory.datagen.create_host_data_with_tags(
        account_number=hbi_default_account_number
    )
    host = test_host_inventory.kafka.create_host(host_data=host_data)

    session = test_host_inventory.application.http_client

    post_data = {
        "tags": [{"namespace": "sat_iam", "key": "hash", "value": "aaabbbaa"}],
        "host_id_list": [host.id],
    }
    url = f"{hbi_ephemeral_base_url}/tags"
    logger.info(f"URL to be used for the test: POST {url}")
    response = session.post(url, json=post_data, verify=False)
    assert response.status_code == 200
    response = test_host_inventory.apis.hosts.get_host_tags_response(host.id)
    assert response.total == 1
    assert len(response.results[host.id]) > len(host_data["tags"])
