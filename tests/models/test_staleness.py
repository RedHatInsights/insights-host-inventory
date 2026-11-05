import pytest
from sqlalchemy import update

from app.exceptions import ValidationException
from app.models import Host
from app.models import db
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid


def test_create_host_sets_per_reporter_staleness(db_create_host, models_datetime_mock):
    input_host = Host(
        subscription_manager_id=generate_uuid(),
        display_name="display_name",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    created_host = db_create_host(host=input_host)

    # per_reporter_staleness now stores only last_check_in timestamp strings
    assert created_host.per_reporter_staleness == {"puptoo": models_datetime_mock.isoformat()}


def test_update_per_reporter_staleness(db_create_host, models_datetime_mock):
    subman_id = generate_uuid()
    input_host = Host(
        subscription_manager_id=subman_id,
        display_name="display_name",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )

    existing_host = db_create_host(host=input_host)

    # per_reporter_staleness now stores only last_check_in timestamp strings
    assert existing_host.per_reporter_staleness == {"puptoo": models_datetime_mock.isoformat()}

    update_host = Host(
        subscription_manager_id=subman_id,
        display_name="display_name",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(update_host)

    # datetime will not change because the datetime.now() method is patched
    assert existing_host.per_reporter_staleness == {"puptoo": models_datetime_mock.isoformat()}

    update_host = Host(
        subscription_manager_id=subman_id,
        display_name="display_name",
        reporter="yupana",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(update_host)

    # datetime will not change because the datetime.now() method is patched
    assert existing_host.per_reporter_staleness == {
        "puptoo": models_datetime_mock.isoformat(),
        "yupana": models_datetime_mock.isoformat(),
    }


@pytest.mark.parametrize("new_reporter", ("satellite", "discovery"))
def test_update_per_reporter_staleness_yupana_replacement(db_create_host, models_datetime_mock, new_reporter):
    subman_id = generate_uuid()
    input_host = Host(
        subscription_manager_id=subman_id,
        display_name="display_name",
        reporter="yupana",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host = db_create_host(host=input_host)

    assert existing_host.per_reporter_staleness == {"yupana": models_datetime_mock.isoformat()}

    update_host = Host(
        subscription_manager_id=subman_id,
        display_name="display_name",
        reporter=new_reporter,
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(update_host)

    # datetime will not change because the datetime.now() method is patched
    # yupana should be removed and replaced with new_reporter
    assert existing_host.per_reporter_staleness == {new_reporter: models_datetime_mock.isoformat()}


def test_reporter_stale_non_string_scalar_errors(db_create_host):
    """Non-string JSONB values must not be treated as stale; reject with ValidationException."""
    host = db_create_host(
        host=Host(
            subscription_manager_id=generate_uuid(),
            display_name="display_name",
            reporter="puptoo",
            org_id=USER_IDENTITY["org_id"],
        )
    )

    db.session.execute(update(Host).where(Host.id == host.id).values(per_reporter_staleness={"puptoo": 42}))
    db.session.commit()
    db.session.refresh(host)

    with pytest.raises(ValidationException, match="expected ISO-8601 string"):
        host.reporter_stale("puptoo")


def test_create_default_staleness_culling(db_create_staleness_culling, db_get_staleness_culling):
    acc_st_cull = db_create_staleness_culling()

    created_acc_st_cull = db_get_staleness_culling(acc_st_cull.org_id)

    assert created_acc_st_cull
    assert created_acc_st_cull.conventional_time_to_stale == acc_st_cull.conventional_time_to_stale
    assert created_acc_st_cull.conventional_time_to_stale_warning == acc_st_cull.conventional_time_to_stale_warning
    assert created_acc_st_cull.conventional_time_to_delete == acc_st_cull.conventional_time_to_delete


def test_create_staleness_culling(db_create_staleness_culling, db_get_staleness_culling):
    acc_st_cull = db_create_staleness_culling(
        conventional_time_to_stale=2 * 86400,
        conventional_time_to_stale_warning=4 * 86400,
        conventional_time_to_delete=20 * 86400,
    )

    created_acc_st_cull = db_get_staleness_culling(acc_st_cull.org_id)
    assert created_acc_st_cull
    assert created_acc_st_cull.conventional_time_to_stale == acc_st_cull.conventional_time_to_stale
    assert created_acc_st_cull.conventional_time_to_stale_warning == acc_st_cull.conventional_time_to_stale_warning
    assert created_acc_st_cull.conventional_time_to_delete == acc_st_cull.conventional_time_to_delete


def test_delete_staleness_culling(db_create_staleness_culling, db_delete_staleness_culling, db_get_staleness_culling):
    acc_st_cull = db_create_staleness_culling()

    created_acc_st_cull = db_get_staleness_culling(acc_st_cull.org_id)
    assert created_acc_st_cull
    db_delete_staleness_culling(created_acc_st_cull.org_id)
    assert not db_get_staleness_culling(acc_st_cull.org_id)


def test_staleness_cache_context_manager():
    """StalenessCache context manager should create and clear cache."""
    from app.models.utils import StalenessCache

    assert StalenessCache.get("org1") is None

    with StalenessCache():
        StalenessCache.put("org1", {"test": True})
        assert StalenessCache.get("org1") == {"test": True}

    assert StalenessCache.get("org1") is None


def test_staleness_cache_eliminates_redundant_queries(flask_app, mocker):  # noqa: ARG001
    """StalenessCache should prevent duplicate Staleness DB queries for the same org_id."""
    from app.models.utils import StalenessCache
    from app.models.utils import get_staleness_obj

    with StalenessCache():
        first_result = get_staleness_obj(USER_IDENTITY["org_id"])
        assert first_result is not None

        mocker.patch("app.models.staleness.Staleness.query")
        second_result = get_staleness_obj(USER_IDENTITY["org_id"])

        assert second_result is first_result
        from app.models.staleness import Staleness

        Staleness.query.filter.assert_not_called()

    assert StalenessCache.get(USER_IDENTITY["org_id"]) is None
