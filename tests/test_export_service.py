import json

import pytest
from marshmallow.exceptions import ValidationError

from app.queue.queue import handle_export_message
from tests.helpers.export_service_utils import create_export_message_missing_field_mock
from tests.helpers.export_service_utils import create_export_message_mock


def test_handle_create_export_request():
    export_message = create_export_message_mock()

    resp = handle_export_message(message=export_message)

    assert resp is True


@pytest.mark.parametrize(
    "field_to_remove", ["id", "source", "subject", "specversion", "type", "time", "redhatorgid", "dataschema", "data"]
)
def test_handle_create_export_missing_field(field_to_remove):
    with pytest.raises(ValidationError):
        export_message = create_export_message_missing_field_mock(field_to_remove)
        handle_export_message(message=export_message)


def test_handle_create_export_wrong_application():
    export_message = create_export_message_mock()
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
