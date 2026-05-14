from __future__ import absolute_import

from urllib.parse import quote

import pytest

from . import common
from . import-helpers as helpers


@pytest.mark.parametrize(
    "filter_value,expected_hosts",
    [
        # Test case 1: URL-encoded asterisk should be treated as a literal
        (quote("abc*123"), ["host-with-literal-star"]),
        # Test case 2: Unencoded asterisk should be a wildcard
        ("abc*123", ["host-with-literal-star", "host-with-wildcard-match"]),
        # Test case 3: URL-encoded backslash and asterisk
        (quote("test1*test2\\test3"), ["host-with-backslash"]),
        # Test case 4: Just a literal star
        (quote("*"), []),
    ],
)
def test_rhineng_4809_wildcard_filtering(
    filter_value, expected_hosts, event_loop, event_producer, query_instance, tables
):
    """
    Test wildcard filtering for system profile fields, ensuring that
    URL-encoded characters are treated as literals.
    """
    system_profile_with_literal_star = {"os_release": "abc*123"}
    host_with_literal_star = helpers.create_host(
        id="host-with-literal-star",
        system_profile=system_profile_with_literal_star,
    )

    system_profile_with_wildcard_match = {"os_release": "abcdef123"}
    host_with_wildcard_match = helpers.create_host(
        id="host-with-wildcard-match",
        system_profile=system_profile_with_wildcard_match,
    )

    system_profile_with_backslash = {"os_release": "test1*test2\\test3"}
    host_with_backslash = helpers.create_host(
        id="host-with-backslash",
        system_profile=system_profile_with_backslash,
    )

    helpers.create_host(id="unrelated-host", system_profile={"os_release": "other"})

    query_string = f"filter[system_profile][os_release]={filter_value}"
    helpers.assert_host_list(
        query_instance,
        expected_hosts,
        query_string=query_string,
        expected_total=len(expected_hosts),
    )
