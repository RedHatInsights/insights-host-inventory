# mypy: disallow-untyped-defs

from collections.abc import Callable

import pytest

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
