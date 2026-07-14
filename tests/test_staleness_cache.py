import json
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from sqlalchemy.orm.exc import NoResultFound

from api.cache import _deserialize_staleness_dict
from api.cache import _staleness_json_default
from api.cache import delete_cached_staleness
from api.cache import get_cached_staleness
from api.cache import set_cached_staleness
from api.staleness_query import get_staleness_obj
from app.models.utils import StalenessCache
from app.staleness_serialization import AttrDict
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import SYSTEM_IDENTITY

SAMPLE_ORG_ID = "test_org_123"
SAMPLE_CREATED_ON = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
SAMPLE_MODIFIED_ON = datetime(2025, 2, 20, 14, 45, 0, tzinfo=UTC)
SAMPLE_STALENESS = AttrDict(
    {
        "id": "some-uuid-1234",
        "org_id": SAMPLE_ORG_ID,
        "conventional_time_to_stale": 86400,
        "conventional_time_to_stale_warning": 604800,
        "conventional_time_to_delete": 1209600,
        "immutable_time_to_stale": 86400,
        "immutable_time_to_stale_warning": 604800,
        "immutable_time_to_delete": 1209600,
        "created_on": SAMPLE_CREATED_ON,
        "modified_on": SAMPLE_MODIFIED_ON,
    }
)


def _make_mock_staleness_model():
    mock = MagicMock()
    mock.id = "db-uuid-5678"
    mock.org_id = SAMPLE_ORG_ID
    mock.conventional_time_to_stale = 86400
    mock.conventional_time_to_stale_warning = 604800
    mock.conventional_time_to_delete = 1209600
    mock.created_on = SAMPLE_CREATED_ON
    mock.modified_on = SAMPLE_MODIFIED_ON
    return mock


def _mock_redis():
    mock_client = MagicMock()
    return patch("api.cache._get_redis_client", return_value=mock_client), mock_client


def _staleness_l2_patches(cache_type: str = "RedisCache", staleness_l2: bool | None = None):
    """Match api.cache init: L2 staleness Redis only when cache type is Redis and flag is on."""
    if staleness_l2 is None:
        staleness_l2 = cache_type == "RedisCache"
    return patch.multiple(
        "api.cache",
        CACHE_CONFIG={"CACHE_TYPE": cache_type},
        STALENESS_L2_CACHE_ENABLED=staleness_l2,
    )


# --- Redis layer (L2) tests ---


def test_datetime_serialization_roundtrip():
    serialized = json.dumps(dict(SAMPLE_STALENESS), default=_staleness_json_default)
    result = _deserialize_staleness_dict(json.loads(serialized))
    assert result["created_on"] == SAMPLE_CREATED_ON
    assert result["modified_on"] == SAMPLE_MODIFIED_ON
    data = dict(SAMPLE_STALENESS, created_on=None, modified_on=None)
    result = _deserialize_staleness_dict(json.loads(json.dumps(data, default=_staleness_json_default)))
    assert result["created_on"] is None


def test_get_and_set_cached_staleness():
    redis_patch, mock_client = _mock_redis()
    with redis_patch, _staleness_l2_patches():
        set_cached_staleness(SAMPLE_ORG_ID, SAMPLE_STALENESS, 3600)
        assert mock_client.set.call_args[1]["ex"] == 3600
        mock_client.get.return_value = mock_client.set.call_args[0][1]
        result = get_cached_staleness(SAMPLE_ORG_ID)
        assert result["org_id"] == SAMPLE_ORG_ID
        assert result["created_on"] == SAMPLE_CREATED_ON
        mock_client.get.return_value = None
        assert get_cached_staleness(SAMPLE_ORG_ID) is None


def test_redis_down_degrades_gracefully():
    redis_patch, mock_client = _mock_redis()
    with redis_patch, _staleness_l2_patches():
        mock_client.get.side_effect = ConnectionError("Redis unavailable")
        assert get_cached_staleness(SAMPLE_ORG_ID) is None


def test_get_cached_staleness_skips_redis_when_cache_disabled():
    redis_patch, mock_client = _mock_redis()
    with redis_patch, _staleness_l2_patches(cache_type="NullCache"):
        result = get_cached_staleness(SAMPLE_ORG_ID)
    assert result is None
    mock_client.get.assert_not_called()


def test_set_cached_staleness_skips_redis_when_cache_disabled():
    redis_patch, mock_client = _mock_redis()
    with redis_patch, _staleness_l2_patches(cache_type="NullCache"):
        set_cached_staleness(SAMPLE_ORG_ID, SAMPLE_STALENESS, 3600)
    mock_client.set.assert_not_called()


def test_delete_cached_staleness_skips_redis_when_cache_disabled():
    redis_patch, mock_client = _mock_redis()
    with redis_patch, _staleness_l2_patches(cache_type="NullCache"):
        delete_cached_staleness(SAMPLE_ORG_ID)
    mock_client.delete.assert_not_called()


def test_staleness_l2_skipped_when_api_redis_but_staleness_flag_disabled():
    """INVENTORY_API_STALENESS_CACHE_ENABLED=false keeps L2 off even if INVENTORY_API_CACHE_TYPE=RedisCache."""
    redis_patch, mock_client = _mock_redis()
    with redis_patch, _staleness_l2_patches(cache_type="RedisCache", staleness_l2=False):
        assert get_cached_staleness(SAMPLE_ORG_ID) is None
        set_cached_staleness(SAMPLE_ORG_ID, SAMPLE_STALENESS, 3600)
        delete_cached_staleness(SAMPLE_ORG_ID)
    mock_client.get.assert_not_called()
    mock_client.set.assert_not_called()
    mock_client.delete.assert_not_called()


# --- StalenessCache L1+L2 integration tests ---


@patch("app.models.utils.get_cached_staleness")
def test_staleness_cache_get_returns_l1_without_redis(mock_redis_get):
    with StalenessCache():
        StalenessCache._local._cache_StalenessCache[SAMPLE_ORG_ID] = SAMPLE_STALENESS
        result = StalenessCache.get(SAMPLE_ORG_ID)
    assert result is SAMPLE_STALENESS
    mock_redis_get.assert_not_called()


@patch("app.models.utils.get_cached_staleness")
def test_staleness_cache_get_falls_back_to_redis_on_l1_miss(mock_redis_get):
    # L1 (thread-local) is empty, so get() should fall back to Redis L2,
    # return the value, and promote it into L1 for subsequent reads.
    mock_redis_get.return_value = SAMPLE_STALENESS
    with StalenessCache():
        result = StalenessCache.get(SAMPLE_ORG_ID)
        l1_value = StalenessCache._local._cache_StalenessCache.get(SAMPLE_ORG_ID)
    assert result is SAMPLE_STALENESS
    assert l1_value is SAMPLE_STALENESS
    mock_redis_get.assert_called_once_with(SAMPLE_ORG_ID)


@patch("app.models.utils.inventory_config")
@patch("app.models.utils.set_cached_staleness")
def test_staleness_cache_put_writes_to_both_layers(mock_redis_set, mock_config):
    mock_config.return_value.staleness_cache_timeout = 3600
    with StalenessCache():
        StalenessCache.put(SAMPLE_ORG_ID, SAMPLE_STALENESS)
        l1_value = StalenessCache._local._cache_StalenessCache.get(SAMPLE_ORG_ID)
    assert l1_value is SAMPLE_STALENESS
    mock_redis_set.assert_called_once_with(SAMPLE_ORG_ID, SAMPLE_STALENESS, 3600)


@patch("app.models.utils.delete_cached_staleness")
def test_staleness_cache_delete_clears_redis(mock_redis_delete):
    StalenessCache.delete(SAMPLE_ORG_ID)
    mock_redis_delete.assert_called_once_with(SAMPLE_ORG_ID)


# --- get_staleness_obj tests ---


@patch.object(StalenessCache, "put")
@patch("api.staleness_query.db")
@patch.object(StalenessCache, "get")
def test_get_staleness_obj_cache_hit_skips_db(mock_get, mock_db, mock_put):
    mock_get.return_value = SAMPLE_STALENESS
    result = get_staleness_obj(SAMPLE_ORG_ID)
    assert result is SAMPLE_STALENESS
    mock_db.session.query.assert_not_called()
    mock_put.assert_not_called()


@patch.object(StalenessCache, "put")
@patch("api.staleness_query.db")
@patch.object(StalenessCache, "get")
def test_get_staleness_obj_cache_miss_populates(mock_get, mock_db, mock_put):
    mock_get.return_value = None
    mock_db.session.query.return_value.filter.return_value.one.return_value = _make_mock_staleness_model()
    result = get_staleness_obj(SAMPLE_ORG_ID)
    assert result["org_id"] == SAMPLE_ORG_ID
    mock_put.assert_called_once()
    put_org_id, put_staleness = mock_put.call_args[0]
    assert put_org_id == SAMPLE_ORG_ID
    assert put_staleness["conventional_time_to_stale"] == 86400


@patch("api.staleness_query.build_staleness_sys_default")
@patch.object(StalenessCache, "put")
@patch("api.staleness_query.db")
@patch.object(StalenessCache, "get")
def test_get_staleness_obj_no_record_uses_default(mock_get, mock_db, mock_put, mock_build_default):
    mock_get.return_value = None
    mock_db.session.query.return_value.filter.return_value.one.side_effect = NoResultFound()
    mock_build_default.return_value = AttrDict({"id": "system_default", "org_id": SAMPLE_ORG_ID})
    result = get_staleness_obj(SAMPLE_ORG_ID)
    assert result["id"] == "system_default"
    mock_put.assert_called_once()


# --- API endpoint tests ---


def test_get_host_uses_cached_staleness(db_create_host, api_get):
    host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}},
    )

    with (
        patch.object(StalenessCache, "get", return_value=SAMPLE_STALENESS) as mock_get,
        patch.object(StalenessCache, "put") as mock_put,
    ):
        url = build_hosts_url(host_list_or_id=host.id)
        response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["results"][0]["id"] == str(host.id)
    mock_get.assert_called_with(SYSTEM_IDENTITY["org_id"])
    mock_put.assert_not_called()


def test_get_host_populates_cache_on_miss(db_create_host, db_create_staleness_culling, api_get):
    host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}},
    )
    db_create_staleness_culling(
        conventional_time_to_stale=86400,
        conventional_time_to_stale_warning=604800,
        conventional_time_to_delete=1209600,
    )

    with (
        patch.object(StalenessCache, "get", return_value=None) as mock_get,
        patch.object(StalenessCache, "put") as mock_put,
    ):
        url = build_hosts_url(host_list_or_id=host.id)
        response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["results"][0]["id"] == str(host.id)
    mock_get.assert_called_with(SYSTEM_IDENTITY["org_id"])
    mock_put.assert_called()
    put_org_id, put_staleness = mock_put.call_args[0]
    assert put_org_id == SYSTEM_IDENTITY["org_id"]
    assert put_staleness["conventional_time_to_stale"] == 86400
    assert put_staleness["conventional_time_to_stale_warning"] == 604800
    assert put_staleness["conventional_time_to_delete"] == 1209600


def test_get_host_returns_correct_staleness_timestamps(db_create_host, api_get):
    host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}},
    )

    with patch.object(StalenessCache, "get", return_value=SAMPLE_STALENESS):
        url = build_hosts_url(host_list_or_id=host.id)
        response_status, response_data = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)
    host_result = response_data["results"][0]

    last_check_in = datetime.fromisoformat(host_result["last_check_in"])
    stale_ts = datetime.fromisoformat(host_result["stale_timestamp"])
    stale_warning_ts = datetime.fromisoformat(host_result["stale_warning_timestamp"])
    culled_ts = datetime.fromisoformat(host_result["culled_timestamp"])
    assert stale_ts == last_check_in + timedelta(seconds=SAMPLE_STALENESS["conventional_time_to_stale"])
    assert stale_warning_ts == last_check_in + timedelta(
        seconds=SAMPLE_STALENESS["conventional_time_to_stale_warning"]
    )
    assert culled_ts == last_check_in + timedelta(seconds=SAMPLE_STALENESS["conventional_time_to_delete"])
