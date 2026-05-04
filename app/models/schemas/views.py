from marshmallow import Schema as MarshmallowSchema
from marshmallow import fields
from marshmallow import pre_load
from marshmallow import validate as marshmallow_validate


class InputViewSchema(MarshmallowSchema):
    name = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=255))
    description = fields.Str(required=False, allow_none=True, validate=marshmallow_validate.Length(max=1024))
    configuration = fields.Dict(required=True)
    org_wide = fields.Bool(required=False, load_default=False)

    @pre_load
    def strip_whitespace_from_name(self, in_data, **kwargs):
        if "name" in in_data and isinstance(in_data["name"], str):
            in_data["name"] = in_data["name"].strip()
        return in_data


class PatchViewSchema(MarshmallowSchema):
    name = fields.Str(required=False, validate=marshmallow_validate.Length(min=1, max=255))
    description = fields.Str(required=False, allow_none=True, validate=marshmallow_validate.Length(max=1024))
    configuration = fields.Dict(required=False)
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
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
