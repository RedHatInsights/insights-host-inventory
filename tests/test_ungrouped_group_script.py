from unittest import mock

import pytest

from app.models import db
from jobs.create_ungrouped_host_groups import run as run_script


@pytest.mark.parametrize("existing_ungrouped", (True, False))
def test_happy_path(
    flask_app,
    db_create_host,
    db_create_group_with_hosts,
    db_get_hosts_for_group,
    db_get_groups_for_host,
    event_producer_mock,
    existing_ungrouped,
):
    EXISTING_GROUP_NAME = "existing group"

    # Create 3 ungrouped hosts & 2 grouped hosts
    ungrouped_host_ids = [db_create_host().id for _ in range(3)]
    grouped_group_id = db_create_group_with_hosts(EXISTING_GROUP_NAME, 2, ungrouped=existing_ungrouped).id
    grouped_host_ids = [host.id for host in db_get_hosts_for_group(grouped_group_id)]
    db.session.commit()

    for host_id in ungrouped_host_ids:
        assert len(db_get_groups_for_host(host_id)) == 0

    for host_id in grouped_host_ids:
        assert db_get_groups_for_host(host_id)[0].name == EXISTING_GROUP_NAME

    run_script(
        logger=mock.MagicMock(),
        session=db.session,
        event_producer=event_producer_mock,
        application=flask_app,
    )

    # All hosts that used to be ungrouped should now be in the "ungrouped" workspace
    # If there was already an existing "ungrouped" group, they should be in that group.
    # Otherwise, they should be in a new "ungrouped" group named "ungrouped".
    ungrouped_group_name = EXISTING_GROUP_NAME if existing_ungrouped else "ungrouped"
    for host_id in ungrouped_host_ids:
        assert db_get_groups_for_host(host_id)[0].name == ungrouped_group_name

    # All hosts that were already in a group should still be in that group
    for host_id in grouped_host_ids:
        assert db_get_groups_for_host(host_id)[0].name == EXISTING_GROUP_NAME
