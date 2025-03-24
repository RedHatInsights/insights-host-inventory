from unittest import mock

import pytest

from app.models import db
from jobs.export_group_data_s3 import run as run_script


@mock.patch("jobs.export_group_data_s3.get_s3_client")
@mock.patch("jobs.export_group_data_s3.GROUPS_BATCH_SIZE", 10)
@pytest.mark.parametrize("num_groups", (0, 1, 5, 21))
def test_happy_path(
    mock_get_s3_client,
    flask_app,
    db_create_group,
    inventory_config,
    num_groups,
):
    # Patch get_s3_client so we can check calls to it
    mock_s3_client = mock.MagicMock()
    mock_get_s3_client.return_value = mock_s3_client

    # Create the groups
    for i in range(num_groups):
        db_create_group(f"test_group_{i}")

    run_script(
        config=inventory_config,
        logger=mock.MagicMock(),
        session=db.session,
        application=flask_app,
    )

    # Make sure the s3 object was sent exactly once
    mock_s3_client.put_object.assert_called_once()

    csv_rows = mock_s3_client.put_object.call_args[1]["Body"].split("\r\n")

    # Check the CSV data
    # Add one for the field header row, add one for EOF
    assert len(csv_rows) == num_groups + 2
