import json
from unittest import mock

import pytest
from marshmallow.exceptions import ValidationError

from app.queue.queue import handle_export_message
from tests.helpers import export_service_utils as es_utils


@mock.patch("app.queue.export_service._handle_rbac_to_export", return_value=es_utils.EXPORT_DATA)
@mock.patch("app.queue.export_service.create_export", return_value=True)
def test_handle_create_export_request_with_data_to_export(mock_export, mock_rbac, inventory_config):
    export_message = es_utils.create_export_message_mock()
    resp = handle_export_message(message=export_message)
    assert resp is True


@mock.patch("app.queue.export_service._handle_rbac_to_export", return_value=[])
@mock.patch("app.queue.export_service.create_export", return_value=False)
def test_handle_create_export_request_with_no_data_to_export(mock_export, mock_rbac, inventory_config):
    export_message = es_utils.create_export_message_mock()
    resp = handle_export_message(message=export_message)
    assert resp is False


@pytest.mark.parametrize(
    "field_to_remove", ["id", "source", "subject", "specversion", "type", "time", "redhatorgid", "dataschema", "data"]
)
def test_handle_create_export_missing_field(field_to_remove):
    with pytest.raises(ValidationError):
        export_message = es_utils.create_export_message_missing_field_mock(field_to_remove)
        handle_export_message(message=export_message)


def test_handle_create_export_wrong_application():
    export_message = es_utils.create_export_message_mock()
    export_message = json.loads(export_message)
    export_message["data"]["resource_request"]["application"] = "foo"
    export_message = json.dumps(export_message)

    resp = handle_export_message(message=export_message)

    assert resp is False


def test_handle_create_export_empty_message():
    with pytest.raises(ValidationError):
        export_message = ""
        export_message = json.dumps(export_message)

        handle_export_message(message=export_message)
