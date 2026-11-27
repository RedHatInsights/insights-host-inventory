import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import acceptance
from iqe_host_inventory.utils.api_utils import criterion_count_eq
from iqe_host_inventory.utils.api_utils import criterion_count_gte
from iqe_host_inventory.utils.api_utils import criterion_total_eq
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import gen_tag_with_parameters
from iqe_host_inventory.utils.datagen_utils import rand_str
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags,search_term",
    [
        # Search term in tag namespace
        (
            [
                gen_tag_with_parameters("k1", "test-namespace1", "test-value1"),
                gen_tag_with_parameters("k2", "test-namespace2", None),
                gen_tag_with_parameters("k3", "test-namespace3", "test-value3"),
            ],
            "nam",
        ),
        # Search term in tag value
        (
            [
                gen_tag_with_parameters("test-k1", "test-ns1", "test-vl1"),
                gen_tag_with_parameters("test-k2", None, "test-vl2"),
                gen_tag_with_parameters("test-k3", None, "test-vl3"),
            ],
            "vl",
        ),
        # Search term in tag key
        (
            [
                gen_tag_with_parameters("key1", None, None),
                gen_tag_with_parameters("key2", "ns2", None),
                gen_tag_with_parameters("key3", "ns3", "vl3"),
            ],
            "key",
        ),
    ],
)
@pytest.mark.parametrize("case_insensitive", [False, True], ids=["correct-case", "wrong-case"])
def test_search_tags(
    host_inventory: ApplicationHostInventory,
    tags: list[TagDict],
    search_term: str,
    case_insensitive: bool,
):
    """
    Create three hosts with one tag associated to each and search through those
    tags.

    1. Create three hosts each one with a tag associated via MQ
    2. Filter the account tags by a search term via REST API
    3. Make sure the expected amount of tags (3) are returned in the response
    4. Make sure the search term is present in at least in one of the
       tag properties (namespace, key or value)

    metadata:
        assignee: fstavela
        importance: high
        title: Confirm that is possible search through tags
    """
    expected_term = search_term.lower()
    hosts_data = [host_inventory.datagen.create_host_data(tags=[tags[i]]) for i in range(3)]
    host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    if case_insensitive:
        search_term = search_term.upper()
    logger.info(f"Searching tags by sending the search term: {search_term}")
    get_tags_response = acceptance(
        host_inventory.apis.tags.get_tags_json,
        search=search_term,
        per_page=3,
        criteria=[(criterion_count_gte, 3)],
    )
    assert get_tags_response["count"] >= 3
    for active_tag in get_tags_response["results"]:
        assert expected_term in convert_tag_to_string(active_tag["tag"]).lower()


@pytest.fixture(scope="class")
def setup_hosts_for_test_tags_total(
    host_inventory: ApplicationHostInventory, hbi_staleness_cleanup_class: None
) -> None:
    hosts_data = []

    for i in range(3):
        host_data = host_inventory.datagen.create_host_data(
            tags=[gen_tag_with_parameters(f"hbi-test-tag-total-{i}")]
        )
        hosts_data.append(host_data)

    create_hosts_fresh_stale(
        host_inventory,
        fresh_hosts_data=hosts_data[0:1] + hosts_data[2:],
        stale_hosts_data=hosts_data[1:2],
        deltas=(5, 3600, 3601),
        cleanup_scope="class",
    )


@pytest.mark.usefixtures("setup_hosts_for_test_tags_total")
class TestTagsTotal:
    @pytest.mark.ephemeral
    @pytest.mark.parametrize(
        "filters,expected_total",
        [
            ({"search": "something-very-strange"}, 0),
            ({"search": "hbi-test-tag-total"}, 3),
            ({"search": "hbi-test-tag-total", "staleness": ["fresh"]}, 2),
            ({"search": "hbi-test-tag-total", "staleness": ["stale"]}, 1),
            ({"search": "hbi-test-tag-total", "staleness": ["fresh", "stale"]}, 3),
            ({"search": "hbi-test-tag-total-0", "staleness": ["fresh", "stale"]}, 1),
        ],
    )
    @pytest.mark.parametrize("case_insensitive", [False, True], ids=["correct-case", "wrong-case"])
    def test_tags_total(
        self,
        host_inventory: ApplicationHostInventory,
        filters: dict[str, str | list[str]],
        expected_total: int,
        case_insensitive: bool,
    ):
        """
        Create three hosts in different states with one tag associated to each and filter
        those tags by a search term and by staleness filter ensuring the total amount of
        tags are returned correctly

        JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-8559

        1. Create three hosts in different culling states each one with a tag associated via MQ
        2. Filter the tags by a search term and by the staleness filter via REST API
        3. Make sure the expected total of tags are returned in the response

        metadata:
            assignee: fstavela
            importance: high
            title: Confirm that the returned total of tags corresponds with the actual number
                of tags returned in the response data
        """
        if case_insensitive:
            filters["search"] = filters["search"].upper()  # type: ignore[union-attr]
        logger.info(f"Searching tags by filtering by: {filters}")
        get_tags_response = acceptance(
            host_inventory.apis.tags.get_tags_json,
            **filters,
            criteria=[(criterion_total_eq, expected_total)],
        )

        assert get_tags_response["total"] == expected_total


@pytest.mark.ephemeral
@pytest.mark.parametrize("case_insensitive", [False, True], ids=["correct-case", "wrong-case"])
def test_search_tags_with_registered_with_filter(
    host_inventory: ApplicationHostInventory,
    case_insensitive: bool,
):
    """
    Ensure that is possible filter tags using the registered_with filter to
    filter out tags from non insights client hosts.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5676

    1. Create two hosts with valid tags, one of which must have its insights_id omitted
    2. Search the tags by sending a search term that matches the tags from both created hosts,
       but also send the filter registered_with = insights to filter out tags
       from non insights client hosts
    3. Make sure only the tags from the host created with an insights_id assigned are returned
    4. Search the tags by sending a search term that matches the tags from both created hosts
    5. Make sure the tags from both created hosts are returned

    metadata:
        assignee: fstavela
        importance: medium
        title: Confirm that is possible search tags using the
            registered_with filter to filter out tags from non insights client hosts
    """
    tag_key = rand_str() + "-test-insights-client-filter"
    tag_insights_client_host = gen_tag_with_parameters(
        namespace=rand_str(), key=tag_key, value=rand_str()
    )
    tag_non_insights_client_host = gen_tag_with_parameters(
        namespace=rand_str(), key=tag_key, value=rand_str()
    )

    logger.info("Creating a host registered with puptoo")
    host_data = host_inventory.datagen.create_host_data(
        tags=[tag_insights_client_host], reporter="puptoo"
    )
    host_inventory.kafka.create_host(host_data)

    logger.info("Creating a host not registered with puptoo")
    host_data = host_inventory.datagen.create_host_data(
        tags=[tag_non_insights_client_host], reporter="test-reporter"
    )
    host_inventory.kafka.create_host(host_data)

    insights_client_str_tag = convert_tag_to_string(tag_insights_client_host)
    if case_insensitive:
        tag_key = tag_key.upper()
    logger.info(
        f"Searching tags by sending the search term: {tag_key} "
        f"using the filter registered_with = puptoo"
    )
    get_tags_response = acceptance(
        host_inventory.apis.tags.get_tags_json,
        search=tag_key,
        registered_with=["puptoo"],
        criteria=[(criterion_count_eq, 1)],
    )
    assert get_tags_response["count"] == 1
    str_result_tag = convert_tag_to_string(get_tags_response["results"][0]["tag"])
    assert insights_client_str_tag == str_result_tag

    non_insights_client_str_tag = convert_tag_to_string(tag_non_insights_client_host)
    logger.info(
        f"Searching tags by sending the search term: {tag_key} "
        f"without using the registered_with filter"
    )
    get_tags_response = acceptance(
        host_inventory.apis.tags.get_tags_json,
        search=tag_key,
        criteria=[(criterion_count_eq, 2)],
    )
    assert get_tags_response["count"] == 2
    result_tags = [convert_tag_to_string(item["tag"]) for item in get_tags_response["results"]]
    assert insights_client_str_tag in result_tags
    assert non_insights_client_str_tag in result_tags


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags, search_term, expected_amount",
    [
        pytest.param(
            [gen_tag_with_parameters("test-key1", "test-namespace1", "test-value1")],
            "nam",
            1,
            id="search term in namespace",
        ),
        pytest.param(
            [
                gen_tag_with_parameters("test-key1", "test-namespace1", "test-value1"),
                gen_tag_with_parameters("test-key2", None, "test-value2"),
            ],
            "value1",
            1,
            id="search term in tag val",
        ),
        pytest.param(
            [
                gen_tag_with_parameters("test-key1", None, None),
                gen_tag_with_parameters("test-key2", "namespace2", None),
                gen_tag_with_parameters("abc3", "namespace3", "value3"),
            ],
            "test",
            2,
            id="search term in key",
        ),
        pytest.param(
            [
                gen_tag_with_parameters(
                    rand_str(),
                    None,
                    rand_str(),
                ),
                gen_tag_with_parameters(rand_str(), rand_str(), rand_str()),
            ],
            "",
            2,
            id="search term empty",
        ),
    ],
)
@pytest.mark.parametrize("case_insensitive", [False, True], ids=["correct-case", "wrong-case"])
def test_search_host_tags(
    host_inventory: ApplicationHostInventory,
    tags: list[TagDict],
    search_term: str,
    expected_amount: int,
    case_insensitive: bool,
):
    """
    Create a host with one or multiple tags and search through those tags.

    1. Create a host with one or multiple tags via MQ
    2. Filter the host's tags by a search term via REST API
    3. Make sure only the expected amount of tags are returned in the response
    4. Make sure the search term is present in at least in one of the
    tag properties (namespace, key or value)

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: Confirm that is possible search through host tags
    """
    expected_term = search_term
    host_data = host_inventory.datagen.create_host_data(tags=tags)
    host = host_inventory.kafka.create_host(host_data)

    if case_insensitive:
        search_term = search_term.upper()
    response = host_inventory.apis.hosts.get_host_tags_response(host.id, search=search_term)

    assert len(response.results[host.id]) == expected_amount

    response_tags = response.results[host.id]
    for tag in response_tags:
        assert expected_term in convert_tag_to_string(tag.to_dict())
