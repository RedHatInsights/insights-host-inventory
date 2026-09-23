from app.models import Host
from app.models import db
from app.tags_blueprint import combine_tags
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


def test_bulk_tag_hosts_noop_skips_write(api_post, db_create_host):
    created_host = db_create_host(extra_data={"tags": {}})
    host_id = str(created_host.id)
    payload = {
        "tags": [{"namespace": "test", "key": "env", "value": "prod"}],
        "host_id_list": [host_id],
    }

    status_code, _ = api_post("/tags", host_data=payload)
    assert status_code == 200
    modified_on_after_first_call = db.session.query(Host).filter(Host.id == host_id).one().modified_on

    status_code, data = api_post("/tags", host_data=payload)
    assert status_code == 200
    assert data["processed_hosts"] == 1

    modified_on_after_second_call = db.session.query(Host).filter(Host.id == host_id).one().modified_on
    assert modified_on_after_second_call == modified_on_after_first_call


def test_bulk_tag_hosts_null_tags_reports_failure(api_post, db_create_host):
    created_host = db_create_host(extra_data={"tags": {}})
    host_id = str(created_host.id)
    # bypass the constructor, which defaults tags=None to {}
    db.session.query(Host).filter(Host.id == created_host.id).update({"tags": None})
    db.session.commit()

    payload = {
        "tags": [{"namespace": "test", "key": "env", "value": "prod"}],
        "host_id_list": [host_id],
    }

    status_code, data = api_post("/tags", host_data=payload)
    assert status_code == 200
    assert data["processed_hosts"] == 0


def test_combine_tags_multiple_items_same_namespace_in_one_call():
    # Guards against a copy-on-write bug where merging namespace N a second time within the
    # same call reads from the pre-call snapshot instead of the just-updated result, silently
    # dropping the first update to that namespace.
    existing = {"test": {"env": ["prod"]}}
    input_list = [
        {"namespace": "test", "key": "env", "value": "staging"},  # append to existing key
        {"namespace": "test", "key": "role", "value": "web"},  # new key, existing namespace
        {"namespace": "test", "key": "role", "value": "web"},  # duplicate within the same call
        {"namespace": "new_ns", "key": "k1", "value": "v1"},  # new namespace
        {"namespace": "new_ns", "key": "k2", "value": "v2"},  # second key, same new namespace
    ]

    result = combine_tags(input_list, existing)

    assert result["test"]["env"] == ["prod", "staging"]
    assert result["test"]["role"] == ["web"]
    assert result["new_ns"]["k1"] == ["v1"]
    assert result["new_ns"]["k2"] == ["v2"]
    # existing_dict must never be mutated
    assert existing == {"test": {"env": ["prod"]}}


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
