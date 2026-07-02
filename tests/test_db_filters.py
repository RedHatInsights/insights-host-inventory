from tests.helpers.api_utils import build_hosts_url


def test_display_name_wildcard_escaping(db_create_host, api_get):
    # Create hosts with special characters in display_name
    host_percent = db_create_host(extra_data={"display_name": "Host%1"})
    host_underscore = db_create_host(extra_data={"display_name": "Host_1"})
    host_backslash = db_create_host(extra_data={"display_name": "Host\\1"})
    host_asterisk = db_create_host(extra_data={"display_name": "HostX1"})

    # 1. Query for percent: should only match host_percent, not host_underscore or host_backslash or host_asterisk
    url = build_hosts_url(query="?display_name=Host%251")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_percent.id) in ids
    assert str(host_underscore.id) not in ids
    assert str(host_backslash.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 2. Query for underscore: should only match host_underscore
    url = build_hosts_url(query="?display_name=Host_1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_underscore.id) in ids
    assert str(host_percent.id) not in ids
    assert str(host_backslash.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 3. Query for backslash: should only match host_backslash
    url = build_hosts_url(query="?display_name=Host%5C1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_backslash.id) in ids
    assert str(host_percent.id) not in ids
    assert str(host_underscore.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 4. Query for asterisk: should match host_asterisk, host_percent, host_underscore, host_backslash
    url = build_hosts_url(query="?display_name=Host*1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_asterisk.id) in ids
    assert str(host_percent.id) in ids
    assert str(host_underscore.id) in ids
    assert str(host_backslash.id) in ids


def test_hostname_or_id_wildcard_escaping(db_create_host, api_get):
    # Create hosts with special characters in fqdn (which is matched by hostname_or_id)
    host_percent = db_create_host(extra_data={"fqdn": "Host%1"})
    host_underscore = db_create_host(extra_data={"fqdn": "Host_1"})
    host_backslash = db_create_host(extra_data={"fqdn": "Host\\1"})
    host_asterisk = db_create_host(extra_data={"fqdn": "HostX1"})

    # 1. Query for percent: should only match host_percent, not host_underscore or host_backslash or host_asterisk
    url = build_hosts_url(query="?hostname_or_id=Host%251")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_percent.id) in ids
    assert str(host_underscore.id) not in ids
    assert str(host_backslash.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 2. Query for underscore: should only match host_underscore
    url = build_hosts_url(query="?hostname_or_id=Host_1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_underscore.id) in ids
    assert str(host_percent.id) not in ids
    assert str(host_backslash.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 3. Query for backslash: should only match host_backslash
    url = build_hosts_url(query="?hostname_or_id=Host%5C1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_backslash.id) in ids
    assert str(host_percent.id) not in ids
    assert str(host_underscore.id) not in ids
    assert str(host_asterisk.id) not in ids

    # 4. Query for asterisk: should match host_asterisk, host_percent, host_underscore, host_backslash
    url = build_hosts_url(query="?hostname_or_id=Host*1")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_asterisk.id) in ids
    assert str(host_percent.id) in ids
    assert str(host_underscore.id) in ids
    assert str(host_backslash.id) in ids
