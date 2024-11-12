import json
from unittest import mock

from requests import exceptions

from app.config import Config
from app.environment import RuntimeEnvironment
from app.models import db
from pendo_syncher import run as pendo_syncher_run
from tests.helpers.test_utils import MockResponseObject


def test_pendo_syncher_request_body(mocker, db_create_host):
    mock_request_function_mock = mocker.patch("pendo_syncher._make_request")

    host = db_create_host()

    request_body = json.dumps([{"accountId": host.org_id, "values": {"hostCount": 1}}])

    config = Config(RuntimeEnvironment.PENDO_JOB)
    config.pendo_sync_active = True

    pendo_syncher_run(config, mock.Mock(), db.session, shutdown_handler=mock.Mock(**{"shut_down.return_value": False}))

    mock_request_function_mock.assert_called_once_with(request_body, config, mock.ANY)


def test_pendo_syncher_response_process(mocker, db_create_host):
    db_create_host()

    mock_response = MockResponseObject()
    mock_response.content = json.dumps({"total": 1, "updated": 1, "failed": 0})

    request_session_post_mock = mocker.patch("pendo_syncher.Session.post")
    request_session_post_mock.side_effect = mock_response

    config = Config(RuntimeEnvironment.PENDO_JOB)
    config.pendo_sync_active = True

    mock_pendo_failure = mocker.patch("pendo_syncher.pendo_failure")
    pendo_syncher_run(config, mock.Mock(), db.session, shutdown_handler=mock.Mock(**{"shut_down.return_value": False}))

    mock_pendo_failure.assert_not_called()


def test_pendo_syncher_response_process_failure(mocker, db_create_host):
    db_create_host()

    mock_response = MockResponseObject()
    mock_response.status_code = 403

    request_session_post_mock = mocker.patch("pendo_syncher.Session.post")
    request_session_post_mock.side_effect = mock_response

    config = Config(RuntimeEnvironment.PENDO_JOB)
    config.pendo_sync_active = True

    mock_pendo_failure = mocker.patch("pendo_syncher.pendo_failure")
    pendo_syncher_run(config, mock.Mock(), db.session, shutdown_handler=mock.Mock(**{"shut_down.return_value": False}))

    mock_call_args = mock_pendo_failure.call_args.args
    assert str(mock_call_args[1]) == "Pendo responded with status 403"


def test_pendo_syncher_exception(mocker, db_create_host):
    request_session_post_mock = mocker.patch("pendo_syncher.Session.post")
    request_session_post_mock.side_effect = Exception("Pendo syncher exception message")

    db_create_host()

    config = Config(RuntimeEnvironment.PENDO_JOB)
    config.pendo_sync_active = True

    mock_pendo_failure = mocker.patch("pendo_syncher.pendo_failure")
    pendo_syncher_run(config, mock.Mock(), db.session, shutdown_handler=mock.Mock(**{"shut_down.return_value": False}))

    mock_call_args = mock_pendo_failure.call_args.args
    assert str(mock_call_args[1]) == "Pendo syncher exception message"


def test_pendo_syncher_retry_error(mocker, db_create_host):
    request_session_post_mock = mocker.patch("pendo_syncher.Session.post")
    request_session_post_mock.side_effect = exceptions.RetryError

    db_create_host()

    config = Config(RuntimeEnvironment.PENDO_JOB)
    config.pendo_sync_active = True

    mock_pendo_failure = mocker.patch("pendo_syncher.pendo_failure")
    pendo_syncher_run(config, mock.Mock(), db.session, shutdown_handler=mock.Mock(**{"shut_down.return_value": False}))

    mock_pendo_failure.assert_called_once()
