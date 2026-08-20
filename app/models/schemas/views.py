from marshmallow import INCLUDE
from marshmallow import Schema as MarshmallowSchema
from marshmallow import fields
from marshmallow import pre_load
from marshmallow import validate as marshmallow_validate

from app.models.views import MAX_VIEW_NAME_LENGTH

VIEW_NAME_PATTERN = r"^[a-zA-Z0-9 _-]+$"
VIEW_NAME_VALIDATION_ERROR = "View name must contain only letters, numbers, spaces, hyphens, and underscores."

_VIEW_NAME_VALIDATION = marshmallow_validate.And(
    marshmallow_validate.Length(min=1, max=MAX_VIEW_NAME_LENGTH),
    marshmallow_validate.Regexp(VIEW_NAME_PATTERN, error=VIEW_NAME_VALIDATION_ERROR),
)


class ColumnSchema(MarshmallowSchema):
    key = fields.Str(required=True, validate=marshmallow_validate.Length(min=1))


class SortSchema(MarshmallowSchema):
    key = fields.Str(required=True, validate=marshmallow_validate.Length(min=1))
    direction = fields.Str(required=True, validate=marshmallow_validate.OneOf(["asc", "desc"]))


VALID_STALENESS_VALUES = ("fresh", "stale", "stale_warning", "unknown")


class HostFiltersSchema(MarshmallowSchema):
    hostname_or_id = fields.Str(required=False)
    staleness = fields.List(
        fields.Str(validate=marshmallow_validate.OneOf(VALID_STALENESS_VALUES)),
        required=False,
    )
    registered_with = fields.List(fields.Str(), required=False)
    tags = fields.List(fields.Str(), required=False)
    workspace_name = fields.List(fields.Str(), required=False)
    last_check_in_start = fields.Str(required=False)
    last_check_in_end = fields.Str(required=False)
    updated_start = fields.Str(required=False)
    updated_end = fields.Str(required=False)
    system_type = fields.List(
        fields.Str(validate=marshmallow_validate.OneOf(["conventional", "bootc", "edge", "cluster"])),
        required=False,
    )


class ViewFiltersSchema(MarshmallowSchema):
    class Meta:
        unknown = INCLUDE

    host = fields.Nested(HostFiltersSchema, required=False)


class ConfigurationSchema(MarshmallowSchema):
    columns = fields.List(fields.Nested(ColumnSchema), required=True)
    sort = fields.Nested(SortSchema, required=False)
    filters = fields.Nested(ViewFiltersSchema, required=False)


class InputViewSchema(MarshmallowSchema):
    name = fields.Str(required=True, validate=_VIEW_NAME_VALIDATION)
    description = fields.Str(required=False, allow_none=True, validate=marshmallow_validate.Length(max=1024))
    configuration = fields.Nested(ConfigurationSchema, required=True)
    org_wide = fields.Bool(required=False, load_default=False)

    @pre_load
    def strip_whitespace_from_name(self, in_data, **kwargs):
        if "name" in in_data and isinstance(in_data["name"], str):
            in_data["name"] = in_data["name"].strip()
        return in_data


class PatchViewSchema(MarshmallowSchema):
    name = fields.Str(required=False, validate=_VIEW_NAME_VALIDATION)
    description = fields.Str(required=False, allow_none=True, validate=marshmallow_validate.Length(max=1024))
    configuration = fields.Nested(ConfigurationSchema, required=False)
    org_wide = fields.Bool(required=False)

    @pre_load
    def strip_whitespace_from_name(self, in_data, **kwargs):
        if "name" in in_data and isinstance(in_data["name"], str):
            in_data["name"] = in_data["name"].strip()
        return in_data


class ViewResponseSchema(MarshmallowSchema):
    id = fields.UUID(dump_only=True)
    org_id = fields.Str(dump_only=True)
    name = fields.Str()
    description = fields.Str(allow_none=True)
    is_system_view = fields.Bool(dump_only=True)
    configuration = fields.Dict()
    org_wide = fields.Bool()
    created_by = fields.Str(dump_only=True, allow_none=True)
    created_on = fields.DateTime(dump_only=True)
    modified_on = fields.DateTime(dump_only=True)
