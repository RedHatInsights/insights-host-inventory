# mypy: disallow-untyped-defs

from collections.abc import Callable
from datetime import datetime

import pytest
from pytest_subtests import SubTests

from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


@pytest.mark.parametrize(
    argnames="field_name,db_attr",
    argvalues=[
        ("created", "created_on"),
        ("updated", "modified_on"),
        ("last_check_in", "last_check_in"),
        ("id", "id"),
    ],
    ids=["created", "updated", "last_check_in", "id"],
)
def test_create_host_ignores_protected_fields(
    mq_create_or_update_host: Callable, db_get_host: Callable, field_name: str, db_attr: str
) -> None:
    fake_value = "this should be ignored"
    host_data = minimal_host(**{field_name: fake_value})
    host = mq_create_or_update_host(host_data)

    db_host = db_get_host(host.id)
    assert db_host is not None
    assert str(getattr(db_host, db_attr)) != fake_value


def test_update_host_preserves_protected_fields(
    mq_create_or_update_host: Callable, db_get_host: Callable, api_get: Callable, subtests: SubTests
) -> None:
    for field in ("created", "updated", "id"):
        with subtests.test(field=field):
            host = minimal_host(insights_id=generate_uuid())
            key, created_event, _ = mq_create_or_update_host(host, return_all_data=True)
            original = created_event["host"]
            host.id = key
            setattr(host, field, generate_uuid() if field == "id" else "2001-01-01T00:00:00+00:00")
            _, event, _ = mq_create_or_update_host(host, return_all_data=True)
            assert event["type"] == "updated"
            assert event["host"]["id"] == key
            assert event["host"]["created"] == original["created"]
            record = db_get_host(key)
            assert str(record.id) == key
            assert record.created_on == datetime.fromisoformat(original["created"])
            status, response = api_get(build_hosts_url(host_list_or_id=key))
            assert status == 200
            assert len(response["results"]) == 1
            persisted = response["results"][0]
            assert persisted["id"] == key
            assert persisted["created"] == original["created"]
            # IQE derives its allowed updated delta from the event, not the caller's value.
            old_updated = datetime.fromisoformat(original["updated"])
            event_updated = datetime.fromisoformat(event["host"]["updated"])
            assert abs(datetime.fromisoformat(persisted["updated"]) - old_updated) <= abs(event_updated - old_updated)
            assert datetime.fromisoformat(persisted["updated"]) == event_updated == record.modified_on
