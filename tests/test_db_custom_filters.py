from tests.helpers.api_utils import build_hosts_url


def test_system_profile_wildcard_escaping(db_create_host, api_get):
    # Create hosts with special characters in insights_client_version
    host_percent = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "Version%1"}})
    host_underscore = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "Version_1"}})
    host_backslash = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "Version\\1"}})
    host_asterisk = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "VersionX1"}})

    # 1. Query for percent: should only match host_percent, not host_underscore or host_backslash or host_asterisk
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=Version%251")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_percent.id) in ids
    assert str(host_underscore.id) not in ids
    assert str(host_backslash.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 2. Query for underscore: should only match host_underscore
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=Version_1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_underscore.id) in ids
    assert str(host_percent.id) not in ids
    assert str(host_backslash.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 3. Query for backslash: should only match host_backslash
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=Version%5C1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_backslash.id) in ids
    assert str(host_percent.id) not in ids
    assert str(host_underscore.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 4. Query for asterisk: should match host_asterisk, host_percent, host_underscore, host_backslash
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=Version*1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_asterisk.id) in ids
    assert str(host_percent.id) in ids
    assert str(host_underscore.id) in ids
    assert str(host_backslash.id) in ids


def test_system_profile_nil_not_nil_not_escaped(db_create_host, api_get):
    # Create a host with insights_client_version key
    host_with_val = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "Version1"}})
    # Create a host without insights_client_version key
    host_without_val = db_create_host(extra_data={"system_profile_facts": {}})

    # 1. Query with nil: should return host_without_val, but not host_with_val
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=nil")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_without_val.id) in ids
    assert str(host_with_val.id) not in ids

    # 2. Query with not_nil: should return host_with_val, but not host_without_val
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=not_nil")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_with_val.id) in ids
    assert str(host_without_val.id) not in ids
