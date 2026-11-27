import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import rand_str
from iqe_host_inventory.utils.tag_utils import convert_tag_from_nested_to_structured
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string
from iqe_host_inventory.utils.tag_utils import sort_tags

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
def test_filter_host_by_tag(host_inventory: ApplicationHostInventory):
    """
    Create a host with tag, filter hosts by tag name.

    1. Create a host with unique tag via MQ
    2. Filter hosts by previously mentioned tag via REST API
    3. Make sure only one host with expected id is found

    metadata:
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
