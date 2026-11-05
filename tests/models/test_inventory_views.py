import uuid
from datetime import UTC
from datetime import datetime

import pytest
from marshmallow import ValidationError as MarshmallowValidationError

from app.exceptions import InventoryException
from app.models import MAX_VIEW_NAME_LENGTH
from app.models import InputViewSchema
from app.models import InventoryView
from app.models import PatchViewSchema
from app.models import ViewResponseSchema

"""
Unit tests for InventoryView model patching and Marshmallow view schemas.
"""


class TestInventoryViewPatch:
    def test_patch_updates_name(self, flask_app):  # noqa: ARG002
        view = InventoryView(name="Old Name", org_id="123", configuration={"filters": {}}, org_wide=False)
        view.description = "Old Desc"

        view.patch({"name": "New Name"})

        assert view.name == "New Name"
        assert view.description == "Old Desc"
        assert view.configuration == {"filters": {}}
        assert view.org_wide is False

    def test_patch_updates_multiple_fields(self, flask_app):  # noqa: ARG002
        view = InventoryView(name="Original", org_id="123", configuration={"columns": ["id"]}, org_wide=False)

        view.patch(
            {
                "name": "Updated",
                "description": "A description",
                "configuration": {"columns": ["id", "display_name"]},
                "org_wide": True,
            }
        )

        assert view.name == "Updated"
        assert view.description == "A description"
        assert view.configuration == {"columns": ["id", "display_name"]}
        assert view.org_wide is True

    def test_patch_empty_data_raises_exception(self, flask_app):  # noqa: ARG002
        view = InventoryView(name="Test", org_id="123", configuration={})

        with pytest.raises(InventoryException):
            view.patch({})

    def test_patch_none_data_raises_exception(self, flask_app):  # noqa: ARG002
        view = InventoryView(name="Test", org_id="123", configuration={})

        with pytest.raises(InventoryException):
            view.patch(None)


class TestInputViewSchema:
    def test_valid_input(self):
        result = InputViewSchema().load(
            {
                "name": "My View",
                "configuration": {"columns": [{"key": "display_name"}]},
            }
        )

        assert result["name"] == "My View"
        assert result["configuration"]["columns"] == [{"key": "display_name"}]
        assert result["org_wide"] is False

    def test_strips_whitespace_from_name(self):
        result = InputViewSchema().load(
            {
                "name": "  Padded Name  ",
                "configuration": {"columns": [{"key": "id"}]},
            }
        )

        assert result["name"] == "Padded Name"

    def test_missing_name_raises_error(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            InputViewSchema().load({"configuration": {"columns": []}})

        assert "name" in exc_info.value.messages

    def test_missing_configuration_raises_error(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            InputViewSchema().load({"name": "Test"})

        assert "configuration" in exc_info.value.messages

    def test_empty_name_raises_error(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            InputViewSchema().load(
                {
                    "name": "",
                    "configuration": {"columns": [{"key": "id"}]},
                }
            )

        assert "name" in exc_info.value.messages

    def test_punctuation_only_name_raises_error(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            InputViewSchema().load(
                {
                    "name": "...",
                    "configuration": {"columns": [{"key": "id"}]},
                }
            )

        assert "name" in exc_info.value.messages

    def test_name_with_periods_and_apostrophes(self):
        result = InputViewSchema().load(
            {
                "name": "Bob's RHEL 9.4",
                "configuration": {"columns": [{"key": "display_name"}]},
            }
        )

        assert result["name"] == "Bob's RHEL 9.4"

    def test_name_too_long_raises_error(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            InputViewSchema().load(
                {
                    "name": "a" * (MAX_VIEW_NAME_LENGTH + 1),
                    "configuration": {"columns": [{"key": "id"}]},
                }
            )

        assert "name" in exc_info.value.messages

    def test_optional_fields(self):
        result = InputViewSchema().load(
            {
                "name": "Test",
                "configuration": {
                    "columns": [{"key": "display_name"}],
                    "sort": {"key": "display_name", "direction": "asc"},
                    "filters": {"os": "RHEL"},
                },
                "description": "A test view",
                "org_wide": True,
            }
        )

        assert result["description"] == "A test view"
        assert result["org_wide"] is True
        assert result["configuration"]["sort"] == {"key": "display_name", "direction": "asc"}
        assert result["configuration"]["filters"]["os"] == "RHEL"

    def test_invalid_sort_direction_raises_error(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            InputViewSchema().load(
                {
                    "name": "Test",
                    "configuration": {
                        "columns": [{"key": "id"}],
                        "sort": {"key": "name", "direction": "invalid"},
                    },
                }
            )

        assert "configuration" in exc_info.value.messages

    def test_missing_columns_raises_error(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            InputViewSchema().load(
                {
                    "name": "Test",
                    "configuration": {},
                }
            )

        assert "configuration" in exc_info.value.messages

    def test_visible_field_rejected(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            InputViewSchema().load(
                {
                    "name": "Test",
                    "configuration": {"columns": [{"key": "display_name", "visible": True}]},
                }
            )

        assert "visible" in str(exc_info.value.messages)


class TestPatchViewSchema:
    def test_all_fields_optional(self):
        result = PatchViewSchema().load({})
        assert result == {}

    def test_partial_update(self):
        result = PatchViewSchema().load({"name": "New Name"})
        assert result == {"name": "New Name"}

    def test_partial_update_configuration(self):
        result = PatchViewSchema().load(
            {
                "configuration": {"columns": [{"key": "id"}]},
            }
        )
        assert result["configuration"]["columns"] == [{"key": "id"}]

    def test_empty_name_still_rejected(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            PatchViewSchema().load({"name": ""})

        assert "name" in exc_info.value.messages

    def test_visible_field_rejected(self):
        with pytest.raises(MarshmallowValidationError) as exc_info:
            PatchViewSchema().load(
                {
                    "configuration": {"columns": [{"key": "id", "visible": False}]},
                }
            )

        assert "visible" in str(exc_info.value.messages)


class TestViewResponseSchema:
    def test_serializes_all_fields(self):
        view_data = {
            "id": uuid.uuid4(),
            "org_id": "8263295",
            "name": "My View",
            "description": None,
            "is_system_view": False,
            "configuration": {"columns": ["display_name"]},
            "org_wide": True,
            "created_by": "addubey",
            "created_on": datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC),
            "modified_on": datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC),
        }

        result = ViewResponseSchema().dump(view_data)

        assert result["name"] == "My View"
        assert result["org_id"] == "8263295"
        assert result["is_system_view"] is False
        assert result["org_wide"] is True
        assert result["created_by"] == "addubey"

    def test_system_view_when_org_id_is_none(self):
        view_data = {
            "id": uuid.uuid4(),
            "org_id": None,
            "name": "Default View",
            "description": "System-wide default",
            "is_system_view": True,
            "configuration": {},
            "org_wide": True,
            "created_by": None,
            "created_on": datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC),
            "modified_on": datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC),
        }

        result = ViewResponseSchema().dump(view_data)

        assert result["org_id"] is None
        assert result["is_system_view"] is True
        assert result["created_by"] is None
