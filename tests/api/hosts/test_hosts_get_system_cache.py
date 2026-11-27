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


@pytest.mark.usefixtures("system_cache")
def test_get_hosts_passes_org_generation_to_cache_key(db_create_host, api_get, mocker):
    insights_id = generate_uuid()
    owner_id = SYSTEM_IDENTITY["system"]["cn"]
    db_create_host(
        SYSTEM_IDENTITY,
        extra_data={"insights_id": insights_id, "system_profile_facts": {"owner_id": owner_id}},
    )
    mocker.patch("api.host.get_system_cache_generations", return_value=(2, 5))
    make_key_spy = mocker.spy(host_api, "make_system_cache_key")

    url = build_hosts_url(query=f"?insights_id={insights_id}")
    status, _ = api_get(url, SYSTEM_IDENTITY)

    assert status == 200
    make_key_spy.assert_called_once()
    assert make_key_spy.call_args.kwargs.get("generation") == 2
    assert make_key_spy.call_args.kwargs.get("org_generation") == 5


@pytest.mark.usefixtures("system_cache")
def test_get_hosts_bypasses_cache_when_org_generation_increments(db_create_host, api_get, mocker):
    insights_id = generate_uuid()
    owner_id = SYSTEM_IDENTITY["system"]["cn"]
    db_create_host(
        SYSTEM_IDENTITY,
        extra_data={"insights_id": insights_id, "system_profile_facts": {"owner_id": owner_id}},
    )
    url = build_hosts_url(query=f"?insights_id={insights_id}")

    # First request: org_generation=0 -> DB is queried and result is cached
    mocker.patch("api.host.get_system_cache_generations", return_value=(0, 0))
    db_lookup_spy = mocker.spy(host_api, "get_host_list_from_db")

    status, first_resp = api_get(url, SYSTEM_IDENTITY)
    assert status == 200
    assert db_lookup_spy.call_count == 1

    # Second request: same org_generation -> served from cache without querying DB
    status, second_resp = api_get(url, SYSTEM_IDENTITY)
    assert status == 200
    assert second_resp == first_resp
    assert db_lookup_spy.call_count == 1

    # Third request: org_generation increments -> cache miss, DB is queried again
    mocker.patch("api.host.get_system_cache_generations", return_value=(0, 1))
    status, third_resp = api_get(url, SYSTEM_IDENTITY)
    assert status == 200
    assert third_resp == first_resp
    assert db_lookup_spy.call_count == 2

    # Fourth request: same new org_generation -> served from updated cache
    status, fourth_resp = api_get(url, SYSTEM_IDENTITY)
    assert status == 200
    assert fourth_resp == first_resp
    assert db_lookup_spy.call_count == 2
