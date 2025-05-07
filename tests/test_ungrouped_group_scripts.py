from unittest import mock

import pytest

from app.models import db
from assign_ungrouped_hosts_to_groups import run as run_assignment_script
from create_ungrouped_host_groups import run as run_creation_script
from delete_ungrouped_host_groups import run as run_undo_script
from tests.helpers.test_utils import SYSTEM_IDENTITY


def test_creation_happy_path(
    flask_app,
    db_create_host,
    db_get_ungrouped_group,
    db_get_groups_for_host,
):
    ungrouped_host_id = db_create_host().id

    # There should not be an ungrouped group yet
    assert db_get_ungrouped_group("test") is None

    run_creation_script(
        logger=mock.MagicMock(),
        session=db.session,
        application=flask_app,
    )

    # The ungrouped group should exist
    assert db_get_ungrouped_group("test") is not None

    # The host should still be ungrouped (unchanged)
    assert db_get_groups_for_host(ungrouped_host_id) == []


@pytest.mark.parametrize("num_ungrouped_hosts", (0, 1, 5, 6))
def test_assignment_happy_path(
    flask_app,
    mocker,
    db_create_host,
    db_create_group_with_hosts,
    db_get_hosts_for_group,
    db_get_groups_for_host,
    event_producer_mock,
    num_ungrouped_hosts,
):
    EXISTING_GROUP_NAME = "existing group"

    # Create some ungrouped hosts & 2 grouped hosts
    ungrouped_host_ids = [db_create_host().id for _ in range(num_ungrouped_hosts)]
    grouped_group_id = db_create_group_with_hosts(EXISTING_GROUP_NAME, 2, ungrouped=True).id
    grouped_host_ids = [host.id for host in db_get_hosts_for_group(grouped_group_id)]
    db.session.commit()

    for host_id in ungrouped_host_ids:
        assert len(db_get_groups_for_host(host_id)) == 0

    for host_id in grouped_host_ids:
        assert db_get_groups_for_host(host_id)[0].name == EXISTING_GROUP_NAME

    # Force a smaller batch size so the test doesn't take ages
    mocker.patch("assign_ungrouped_hosts_to_groups.BATCH_SIZE", 5)

    run_assignment_script(
        logger=mock.MagicMock(),
        session=db.session,
        event_producer=event_producer_mock,
        application=flask_app,
    )

    # All hosts that used to be ungrouped should now be in the "ungrouped" workspace
    # If there was already an existing "ungrouped" group, they should be in that group.
    # Otherwise, they should be in a new "ungrouped" group named "ungrouped".
    for host_id in ungrouped_host_ids:
        assert db_get_groups_for_host(host_id)[0].name == EXISTING_GROUP_NAME
        assert db_get_groups_for_host(host_id)[0].ungrouped is True
        assert db_get_groups_for_host(host_id)[0].account == SYSTEM_IDENTITY["account_number"]

    # All hosts that were already in a group should still be in that group
    for host_id in grouped_host_ids:
        assert db_get_groups_for_host(host_id)[0].name == EXISTING_GROUP_NAME


def test_undo_happy_path(
    db_create_group_with_hosts, db_get_hosts_for_group, db_get_groups_for_host, event_producer_mock, flask_app
):
    UNGROUPED_GROUP_NAME = "Ungrouped Hosts"

    # Create an "ungrouped" group and assign 3 hosts to it
    ungrouped_group_id = db_create_group_with_hosts(UNGROUPED_GROUP_NAME, 3, ungrouped=True).id
    grouped_host_ids = [host.id for host in db_get_hosts_for_group(ungrouped_group_id)]
    db.session.commit()

    # All hosts should be in the "ungrouped" group before running the script
    for host_id in grouped_host_ids:
        groups = db_get_groups_for_host(host_id)
        assert len(groups) == 1
        assert groups[0].name == UNGROUPED_GROUP_NAME
        assert groups[0].ungrouped is True

    run_undo_script(
        logger=mock.MagicMock(),
        session=db.session,
        event_producer=event_producer_mock,
        application=flask_app,
    )

    db.session.commit()

    # All hosts that were in the "ungrouped" group should now not be in any group
    for host_id in grouped_host_ids:
        assert db_get_groups_for_host(host_id) == []
