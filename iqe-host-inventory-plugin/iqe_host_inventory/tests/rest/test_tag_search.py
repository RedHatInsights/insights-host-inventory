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
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale_stalewarning
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
        requirements: inv-tags-get-list
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
        host_inventory.apis.tags.get_tags_response,
        search=search_term,
        per_page=3,
        criteria=[(criterion_count_gte, 3)],
    )
    assert get_tags_response.count >= 3
    for active_tag in get_tags_response.results:
        assert expected_term in convert_tag_to_string(active_tag.tag.to_dict()).lower()


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
            requirements: inv-tags-get-list
            assignee: fstavela
            importance: high
            title: Confirm that the returned total of tags corresponds with the actual number
                of tags returned in the response data
        """
        if case_insensitive:
            filters["search"] = filters["search"].upper()  # type: ignore[union-attr]
        logger.info(f"Searching tags by filtering by: {filters}")
        get_tags_response = acceptance(
            host_inventory.apis.tags.get_tags_response,
            **filters,
            criteria=[(criterion_total_eq, expected_total)],
        )

        assert get_tags_response.total == expected_total


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags",
    [
        [
            gen_tag_with_parameters(
                namespace=rand_str(),
                key=rand_str() + "test",
                value=rand_str() + "test-tag",
            )
        ],
        [
            gen_tag_with_parameters(
                namespace=" " + rand_str(),
                key=rand_str() + " test",
                value=rand_str() + "test tag",
            )
        ],
        [gen_tag_with_parameters(key="test-key-&+0@%$")],
        [gen_tag_with_parameters(namespace=None, key="test-𝗤Ɍ𝓢ȚЦ𝒱Ѡ𝓧ƳȤ")],
        [gen_tag_with_parameters(namespace=None, key="test-Ça}{?:", value=None)],
        [
            gen_tag_with_parameters(
                namespace="test-+[{]};:",
                key="test-+(!*%",
                value="test-٤ḞԍНǏ𝙅ƘԸⲘ𝙉০",
            )
        ],
    ],
)
@pytest.mark.parametrize("case_insensitive", [False, True], ids=["correct-case", "wrong-case"])
def test_search_tags_with_multiple_search_term_combinations(
    host_inventory: ApplicationHostInventory,
    tags: list[TagDict],
    case_insensitive: bool,
):
    """
    Ensure that is possible filter tags by multiple search term combinations.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5676

    1. Create a new host with a valid tag combination
    2. Filter the account tags by multiple search term combinations
    3. Ensure the expected tags are returned as result of the query

    metadata:
        requirements: inv-tags-get-list
        assignee: fstavela
        importance: high
        title: Confirm that is possible search through the tags using
            multiple search term combinations
    """
    host_data = host_inventory.datagen.create_host_data(tags=tags)
    host_inventory.kafka.create_host(host_data=host_data)

    search_tag = tags[0]
    # Search tags by its namespace, key or value
    for key, value in {k: v for (k, v) in search_tag.items() if v}.items():
        if case_insensitive:
            value = value.upper()  # type: ignore[attr-defined]
        logger.info(f"Searching tags by sending the search term: {value}")
        get_tags_response = acceptance(
            host_inventory.apis.tags.get_tags_response,
            search=value,
            per_page=1,
            criteria=[(criterion_count_eq, 1)],
        )
        assert get_tags_response.count == 1
        str_tag = convert_tag_to_string(search_tag)
        str_result_tag = convert_tag_to_string(get_tags_response.results[0].tag.to_dict())
        assert search_tag[key] in str_result_tag  # type: ignore[literal-required]
        assert str_result_tag == str_tag

    # Search tags by a combination of namespace, key and value
    str_tag = convert_tag_to_string(search_tag)
    search_str_tag = str_tag.upper() if case_insensitive else str_tag
    logger.info(f"Searching tags by sending the search term: {str_tag}")
    get_tags_response = acceptance(
        host_inventory.apis.tags.get_tags_response,
        search=search_str_tag,
        per_page=1,
        criteria=[(criterion_count_eq, 1)],
    )
    assert get_tags_response.count == 1
    str_result_tag = convert_tag_to_string(get_tags_response.results[0].tag.to_dict())
    assert str_tag == str_result_tag


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
        requirements: inv-tags-get-list, inv-hosts-filter-by-registered_with
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
        host_inventory.apis.tags.get_tags_response,
        search=tag_key,
        registered_with=["puptoo"],
        criteria=[(criterion_count_eq, 1)],
    )
    assert get_tags_response.count == 1
    str_result_tag = convert_tag_to_string(get_tags_response.results[0].tag.to_dict())
    assert insights_client_str_tag == str_result_tag

    non_insights_client_str_tag = convert_tag_to_string(tag_non_insights_client_host)
    logger.info(
        f"Searching tags by sending the search term: {tag_key} "
        f"without using the registered_with filter"
    )
    get_tags_response = acceptance(
        host_inventory.apis.tags.get_tags_response,
        search=tag_key,
        criteria=[(criterion_count_eq, 2)],
    )
    assert get_tags_response.count == 2
    result_tags = [convert_tag_to_string(item.tag.to_dict()) for item in get_tags_response.results]
    assert insights_client_str_tag in result_tags
    assert non_insights_client_str_tag in result_tags


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
@pytest.mark.parametrize("case_insensitive", [False, True], ids=["correct-case", "wrong-case"])
def test_search_tags_with_staleness_filter(
    host_inventory: ApplicationHostInventory,
    case_insensitive: bool,
):
    """
    Ensure that is possible filter tags using the staleness filter to filter
    tags from hosts in different states.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5676

    1. Create three hosts with valid tags in
       three different states (fresh, stale and stale_warning)
    2. Search the tags by sending a search term that matches the tags from all of the
       created hosts, but also send the staleness filter to return the tags from hosts
       in a specific state
    3. Make sure only the tags from the hosts in the specific state are returned as result
    4. Search the tags by sending a search term that matches the tags from all of the
       created hosts, but also send the staleness filter with all the possible values
       (staleness=[fresh, stale, stale_warning])
    5. Make sure the tags from all of the three hosts are returned as result

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-staleness
        assignee: fstavela
        importance: high
        title: Confirm that is possible search tags using the
            staleness filter to filter tags from hosts in different states
    """

    tag_key = rand_str() + "-test-staleness-filter"
    tags = {
        "fresh": gen_tag_with_parameters(rand_str(), tag_key, rand_str()),
        "stale": gen_tag_with_parameters(rand_str(), tag_key, rand_str()),
        "stale_warning": gen_tag_with_parameters(rand_str(), tag_key, rand_str()),
    }

    logger.info("Creating three hosts in different states (fresh, stale and stale_warning)")
    hosts_data = []
    for tag in tags.values():
        hosts_data.append(host_inventory.datagen.create_host_data(tags=[tag]))

    create_hosts_fresh_stale_stalewarning(
        host_inventory,
        fresh_hosts_data=hosts_data[:1],
        stale_hosts_data=hosts_data[1:2],
        stale_warning_hosts_data=hosts_data[2:],
    )

    if case_insensitive:
        tag_key = tag_key.upper()
    for host_state, tag in tags.items():
        logger.info(
            f"Search tags by sending the search term: {tag_key} "
            f"and the filter staleness={host_state}"
        )
        get_tags_response = acceptance(
            host_inventory.apis.tags.get_tags_response,
            search=tag_key,
            staleness=[host_state],
            criteria=[(criterion_count_eq, 1)],
        )
        assert get_tags_response.count == 1
        str_result_tag = convert_tag_to_string(get_tags_response.results[0].tag.to_dict())
        assert convert_tag_to_string(tag) in str_result_tag

    logger.info(
        f"Search tags by sending the search term: {tag_key}"
        f"and the filter staleness=[fresh, stale, stale_warning]"
    )
    get_tags_response = acceptance(
        host_inventory.apis.tags.get_tags_response,
        search=tag_key,
        staleness=["fresh", "stale", "stale_warning"],
        criteria=[(criterion_count_eq, 3)],
    )
    assert get_tags_response.count == 3
    result_tags = [convert_tag_to_string(item.tag.to_dict()) for item in get_tags_response.results]
    for tag in tags.values():
        assert convert_tag_to_string(tag) in result_tags


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
        requirements: inv-hosts-get-tags
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


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "tags,search_term",
    [
        pytest.param(
            [gen_tag_with_parameters(rand_str(), rand_str(), rand_str())],
            rand_str(min_chars=256, max_chars=500),
            id="random_search too long",
        ),
        pytest.param(
            [
                gen_tag_with_parameters(rand_str(), None, rand_str()),
                gen_tag_with_parameters(rand_str(), None, None),
            ],
            ".",
            id="dot is invaluid",
        ),
        pytest.param(
            [
                gen_tag_with_parameters(rand_str(), None, None),
                gen_tag_with_parameters(rand_str(), rand_str(), None),
                gen_tag_with_parameters(rand_str(), rand_str(), rand_str()),
            ],
            rand_str(min_chars=10, max_chars=20),
            id="too_short",
        ),
    ],
)
def test_search_host_tags_with_invalid_terms(
    host_inventory: ApplicationHostInventory,
    tags: list[TagDict],
    search_term: str,
):
    """
    Create a host with one or multiple tags and search through those tags using
    invalid terms.

    1. Create a host with one or multiple tags via MQ
    2. Filter the host's tags by an invalid search term via REST API
    3. Make sure NO tag is being returned in the response

    metadata:
        requirements: inv-hosts-get-tags, inv-api-validation
        assignee: fstavela
        importance: medium
        title: Inventory: tags search using invalid terms return empty result
    """
    host_data = host_inventory.datagen.create_host_data(tags=tags)
    host = host_inventory.kafka.create_host(host_data)

    response = host_inventory.apis.hosts.get_host_tags_response(host.id, search=search_term)
    assert len(response.results[host.id]) == 0
