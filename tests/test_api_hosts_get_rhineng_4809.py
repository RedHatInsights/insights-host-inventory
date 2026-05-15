
from tests.helpers.api_utils import build_hosts_url


def test_rhineng_4809_backslash_escaping_in_wildcard_filter(db_create_host, api_get):
    """
    Tests that backslashes are properly escaped in wildcard filters for system profiles.
    This test case is based on the scenario described in RHINENG-4809.
    """
    # Create a host with a system profile value containing a backslash followed by a 't'.
    # This is problematic if the backslash is not escaped, as '\t' is a special character.
    sp_data = {"system_profile_facts": {"os_release": "text\\text"}}
    host_id = str(db_create_host(extra_data=sp_data).id)

    # The filter query uses a wildcard '*' at the end.
    # The value "text\text*" is URL-encoded to "text%5Ctext*".
    # After decoding by the web framework, the application receives "text\text*".
    #
    # Without the fix, the backslash is not escaped for the SQL ILIKE query,
    # and the pattern becomes 'text\text%'. In PostgreSQL, '\t' is interpreted
    # as a tab character, so the query looks for 'text<tab>ext%', which does not match.
    #
    # With the fix, the backslash is escaped, and the pattern becomes 'text\\text%',
    # which correctly matches the host's os_release value.
    query = "?filter[system_profile][os_release]=text%5Ctext*"
    url = build_hosts_url(query=query)
    response_status, response_data = api_get(url)

    assert response_status == 200, "API request should be successful"
    assert response_data["total"] == 1, "Should find one host matching the backslash pattern"
    assert response_data["results"][0]["id"] == host_id, "The correct host should be returned"


def test_rhineng_4809_url_encoded_wildcard_as_literal(db_create_host, api_get):
    """
    Tests that a URL-encoded wildcard character '*' is treated as a literal character
    in system profile filters, as per RHINENG-4809.
    """
    # Create a host with a literal asterisk in its os_release value.
    sp_data = {"system_profile_facts": {"os_release": "text*text"}}
    host_id = str(db_create_host(extra_data=sp_data).id)

    # Create other hosts that would match if '*' were treated as a wildcard.
    db_create_host(extra_data={"system_profile_facts": {"os_release": "text-a-text"}})
    db_create_host(extra_data={"system_profile_facts": {"os_release": "text-b-text"}})

    # The filter query for a literal '*' is "text\*text".
    # This is URL-encoded to "text%5C*text".
    query = "?filter[system_profile][os_release]=text%5C*text"
    url = build_hosts_url(query=query)
    response_status, response_data = api_get(url)

    assert response_status == 200, "API request should be successful"
    assert response_data["total"] == 1, "Should find only the host with the literal asterisk"
    assert response_data["results"][0]["id"] == host_id, "The correct host should be returned"
