import io
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

import delete_hosts_s3
from app.config import Config

# Patch constants and functions used in run
BATCH_SIZE = 2
S3_OBJECT_KEY = "host_ids.csv"


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.exception = MagicMock()
    return logger


@pytest.fixture
def mock_config():
    config = MagicMock(spec=Config)
    config.s3_bucket = "test-bucket"
    config.dry_run = False
    return config


@pytest.fixture
def mock_session():
    return MagicMock(spec=["query", "commit"])


@pytest.fixture
def mock_s3_client():
    return MagicMock()


@pytest.fixture
def patch_get_s3_client(mock_s3_client):
    with patch("delete_hosts_s3.get_s3_client", return_value=mock_s3_client):
        yield mock_s3_client


@pytest.fixture
def patch_process_batch():
    with patch("delete_hosts_s3.process_batch") as mock_proc:
        yield mock_proc


@pytest.fixture
def patch_globals(monkeypatch):
    # Patch the global counters
    monkeypatch.setattr("delete_hosts_s3.BATCH_SIZE", BATCH_SIZE)
    monkeypatch.setattr("delete_hosts_s3.S3_OBJECT_KEY", S3_OBJECT_KEY)
    monkeypatch.setattr("delete_hosts_s3.not_deleted_count", 0)
    monkeypatch.setattr("delete_hosts_s3.not_found_count", 0)
    monkeypatch.setattr("delete_hosts_s3.deleted_count", 0)


@pytest.mark.usefixtures("patch_globals")
@pytest.mark.parametrize(
    "csv_content, dry_run, expected_batches, expected_final_log",
    [
        (
            "header\nid1\nid2\nid3\nid4\n",
            False,
            [["id1", "id2"], ["id3", "id4"]],
            "Hosts that were not deleted because they had multiple reporters: 0",
        ),
        (
            "header\nid1\nid2\nid3\n",
            True,
            [["id1", "id2"], ["id3"]],
            "This was a dry run. This many hosts would have been deleted in an actual run: 0",
        ),
        (
            "header\n\nid1\n\n",
            False,
            [["id1"]],
            "Hosts that were not deleted because they had multiple reporters: 0",
        ),
    ],
)
def test_run_happy_and_edge_cases(
    csv_content,
    dry_run,
    expected_batches,
    expected_final_log,
    mock_config,
    mock_logger,
    mock_session,
    flask_app,
    patch_get_s3_client,
    patch_process_batch,
    monkeypatch,
    event_producer,
    notification_event_producer,
):
    # Arrange
    mock_config.dry_run = dry_run
    # Provide a real BytesIO stream, as the production code expects a file-like object for io.TextIOWrapper
    s3_body = io.BytesIO(csv_content.encode("utf-8"))
    patch_get_s3_client.get_object.return_value = {"Body": s3_body}

    # Patch the global counters for logging
    monkeypatch.setattr("delete_hosts_s3.not_deleted_count", 0)
    monkeypatch.setattr("delete_hosts_s3.not_found_count", 0)
    monkeypatch.setattr("delete_hosts_s3.deleted_count", 0)

    # Act
    delete_hosts_s3.run(mock_config, mock_logger, mock_session, event_producer, notification_event_producer, flask_app)

    # Assert
    actual_batches = [call[0][0] for call in patch_process_batch.call_args_list]
    assert actual_batches == expected_batches
    assert any(expected_final_log in str(c[0][0]) for c in mock_logger.info.call_args_list)


@pytest.mark.usefixtures("patch_globals", "patch_process_batch")
@pytest.mark.parametrize(
    "exception_type",
    (Exception, RuntimeError),
)
def test_run_exception_handling(
    exception_type,
    mock_config,
    mock_logger,
    mock_session,
    flask_app,
    patch_get_s3_client,
    event_producer,
    notification_event_producer,
):
    # Arrange
    patch_get_s3_client.get_object.side_effect = exception_type("fail!")

    # Act
    delete_hosts_s3.run(mock_config, mock_logger, mock_session, event_producer, notification_event_producer, flask_app)

    # Assert
    assert mock_logger.exception.called
    patch_get_s3_client.close.assert_called_once()


@pytest.mark.usefixtures("patch_globals", "patch_process_batch")
def test_run_finally_always_closes_s3(
    mock_config, mock_logger, mock_session, flask_app, patch_get_s3_client, event_producer, notification_event_producer
):
    # Arrange
    s3_body = io.BytesIO(b"id1\n")
    patch_get_s3_client.get_object.return_value = {"Body": s3_body}

    # Act
    delete_hosts_s3.run(mock_config, mock_logger, mock_session, event_producer, notification_event_producer, flask_app)

    # Assert
    patch_get_s3_client.close.assert_called_once()


@pytest.mark.usefixtures("patch_globals", "patch_process_batch")
def test_run_handles_app_context(
    mock_config, mock_logger, mock_session, patch_get_s3_client, event_producer, notification_event_producer
):
    # Arrange
    s3_body = io.BytesIO(b"id1\n")
    patch_get_s3_client.get_object.return_value = {"Body": s3_body}
    mock_app = MagicMock()
    mock_ctx = MagicMock()
    mock_app.app.app_context.return_value = mock_ctx

    # Act
    delete_hosts_s3.run(mock_config, mock_logger, mock_session, event_producer, notification_event_producer, mock_app)

    # Assert
    mock_app.app.app_context.assert_called_once()
    mock_ctx.__enter__.assert_called_once()
    mock_ctx.__exit__.assert_called_once()
