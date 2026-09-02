import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url


def test_get_total_default(_mq_create_three_specific_hosts, api_get):
    """
    By default, get_total is true, so total should be returned as the actual count.
    """
    url = build_hosts_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] == 3


def test_get_total_explicit_true(_mq_create_three_specific_hosts, api_get):
    """
    When get_total=true, total should be returned as the actual count.
    """
    url = build_hosts_url(query="?get_total=true")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] == 3


def test_get_total_explicit_false(_mq_create_three_specific_hosts, api_get):
    """
    When get_total=false, total should be returned as None (null).
    """
    url = build_hosts_url(query="?get_total=false")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] is None


def test_get_total_invalid_value(api_get):
    """
    When get_total is an invalid boolean, it should return 400 Bad Request.
    """
    url = build_hosts_url(query="?get_total=not_a_boolean")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=400)


def test_get_total_false_still_returns_hosts(_mq_create_three_specific_hosts, api_get):
    """
    When get_total=false, hosts should still be returned even though total is null.
    """
    url = build_hosts_url(query="?get_total=false")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] is None
    assert response_data["count"] == 3
    assert len(response_data["results"]) == 3


def test_get_total_false_with_pagination(_mq_create_three_specific_hosts, api_get):
    """
    When get_total=false with pagination, total is null but pagination still works.
    """
    url = build_hosts_url(query="?get_total=false&per_page=2&page=1")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] is None
    assert response_data["count"] == 2
    assert len(response_data["results"]) == 2
    assert response_data["per_page"] == 2
    assert response_data["page"] == 1


def test_get_total_true_with_pagination(_mq_create_three_specific_hosts, api_get):
    """
    When get_total=true with pagination, total reflects the actual count.
    """
    url = build_hosts_url(query="?get_total=true&per_page=2&page=1")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] == 3
    assert response_data["count"] == 2
    assert len(response_data["results"]) == 2


def test_get_total_false_no_hosts(api_get):
    """
    When get_total=false and no hosts exist, total is null and results are empty.
    """
    url = build_hosts_url(query="?get_total=false")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] is None
    assert response_data["count"] == 0
    assert len(response_data["results"]) == 0


def test_get_total_default_no_hosts(api_get):
    """
    When get_total is default (true) and no hosts exist, total is 0.
    """
    url = build_hosts_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] == 0
    assert response_data["count"] == 0


def test_get_total_false_with_display_name_filter(mq_create_three_specific_hosts, api_get):
    """
    When get_total=false with a filter, total is null but filtered results are returned.
    """
    created_hosts = mq_create_three_specific_hosts
    display_name = created_hosts[0].display_name
    url = build_hosts_url(query=f"?get_total=false&display_name={display_name}")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert response_data["total"] is None
    assert response_data["count"] >= 1


@pytest.mark.parametrize(
    "get_total_value,expected_total_type",
    [
        ("true", int),
        ("True", int),
        ("false", type(None)),
        ("False", type(None)),
    ],
)
def test_get_total_case_insensitive(
    _mq_create_three_specific_hosts,
    api_get,
    get_total_value,
    expected_total_type,
):
    """
    The get_total param should accept case-insensitive boolean strings.
    """
    url = build_hosts_url(query=f"?get_total={get_total_value}")
    response_status, response_data = api_get(url)
    assert_response_status(response_status, expected_status=200)
    assert isinstance(response_data["total"], expected_total_type)
