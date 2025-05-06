from tests.helpers.test_utils import generate_uuid


def test_bulk_tag_hosts_success(api_post, db_create_host):
    created_host_1 = db_create_host(extra_data={"tags": {"ns1": {"key1": "value1"}}})
    created_host_2 = db_create_host(extra_data={"tags": {"ns1": {"key2": "value2"}}})
    created_host_3 = db_create_host(extra_data={"tags": {}})
    db_hosts = [str(created_host_1.id), str(created_host_2.id), str(created_host_3.id)]
    payload = {
        "tags": [
            {"namespace": "test", "key": "env", "value": "prod"},
            {"namespace": "test", "key": "role", "value": "server"},
        ],
        "host_id_list": db_hosts[:2],
    }

    status_code, data = api_post("/tags", host_data=payload)
    assert status_code == 200

    assert data["processed_hosts"] == 2
    assert data["total_hosts"] == 2
    assert data["not_found_hosts"] == []


def test_bulk_tag_hosts_some_not_found(api_post, db_create_host):
    created_host_1 = db_create_host(extra_data={"tags": {"ns1": {"key1": "value1"}}})
    created_host_2 = db_create_host(extra_data={"tags": {"ns1": {"key2": "value2"}}})
    created_host_3 = db_create_host(extra_data={"tags": {}})
    db_hosts = [str(created_host_1.id), str(created_host_2.id), str(created_host_3.id)]
    payload = {
        "tags": [{"namespace": "test", "key": "env", "value": "prod"}],
        "host_id_list": [db_hosts[0], generate_uuid()],
    }

    status_code, data = api_post("/tags", host_data=payload)
    assert status_code == 200

    assert data["processed_hosts"] == 1
    assert data["total_hosts"] == 2
    assert len(data["not_found_hosts"]) == 1
    assert "Some hosts were not found" in data["warning"]


def test_bulk_tag_hosts_empty_tags(api_post, db_create_host):
    created_host_1 = db_create_host(extra_data={"tags": {"ns1": {"key1": "value1"}}})
    created_host_2 = db_create_host(extra_data={"tags": {"ns1": {"key2": "value2"}}})
    created_host_3 = db_create_host(extra_data={"tags": {}})
    db_hosts = [str(created_host_1.id), str(created_host_2.id), str(created_host_3.id)]
    payload = {"tags": [], "host_id_list": [db_hosts[0]]}

    status_code, data = api_post("/tags", host_data=payload)
    assert status_code == 400
    assert "Missing required field: tags" in data["error"]


def test_bulk_tag_hosts_empty_host_list(api_post):
    payload = {"tags": [{"namespace": "test", "key": "env", "value": "prod"}], "host_id_list": []}

    status_code, data = api_post("/tags", host_data=payload)
    assert status_code == 400
    assert "Missing required field: host_id_list" in data["error"]


def test_bulk_tag_hosts_too_many_tags(api_post, db_create_host):
    created_host_1 = db_create_host(extra_data={"tags": {"ns1": {"key1": "value1"}}})
    created_host_2 = db_create_host(extra_data={"tags": {"ns1": {"key2": "value2"}}})
    created_host_3 = db_create_host(extra_data={"tags": {}})
    db_hosts = [str(created_host_1.id), str(created_host_2.id), str(created_host_3.id)]
    payload = {
        "tags": [{"namespace": "test", "key": f"key{i}", "value": "value"} for i in range(11)],
        "host_id_list": [db_hosts[0]],
    }

    status_code, data = api_post("/tags", host_data=payload)
    assert status_code == 400
    assert "Too many tags provided" in data["error"]
