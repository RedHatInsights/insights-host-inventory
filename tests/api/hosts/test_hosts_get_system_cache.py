import pytest
from flask_caching import Cache

import api.cache as cache_module
import api.host as host_api
from api.cache_key import make_system_cache_key
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid


@pytest.fixture
def system_cache(flask_app, monkeypatch):
    cache = Cache(config={"CACHE_TYPE": "SimpleCache"})
    cache.init_app(flask_app.app, config={"CACHE_TYPE": "SimpleCache"})
    monkeypatch.setattr(cache_module, "CACHE", cache)
    monkeypatch.setattr(cache_module, "CACHE_CONFIG", {"CACHE_TYPE": "SimpleCache"})
    monkeypatch.setattr(host_api, "CACHE", cache)
    return cache


def test_get_hosts_normalizes_uuids_before_caching(system_cache, db_create_host, api_get, mocker):
    insights_id = generate_uuid()
    owner_id = SYSTEM_IDENTITY["system"]["cn"]
    host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={"insights_id": insights_id, "system_profile_facts": {"owner_id": owner_id}},
    )
    key = make_system_cache_key(insights_id, SYSTEM_IDENTITY["org_id"], owner_id, generation=0)
    url = build_hosts_url(query=f"?insights_id={insights_id}")
    serialize_host = host_api.serialize_host_with_params
    mocker.patch(
        "api.host.serialize_host_with_params", side_effect=lambda record: {**serialize_host(record), "id": record.id}
    )

    status, expected = api_get(url, SYSTEM_IDENTITY)

    assert status == 200
    assert system_cache.get(key)["id"] == str(host.id)
    database_lookup = mocker.patch("api.host.get_host_list_from_db")

    status, response = api_get(url, SYSTEM_IDENTITY)

    assert status == 200
    assert response == expected
    database_lookup.assert_not_called()
