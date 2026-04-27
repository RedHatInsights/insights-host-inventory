from marshmallow import Schema as MarshmallowSchema
from marshmallow import fields
from marshmallow import validate as marshmallow_validate


class PatchDataSchema(MarshmallowSchema):
    """Schema for Patch application data."""

    # Advisory counts by type (applicable)
    advisories_rhsa_applicable = fields.Int(allow_none=True)
    advisories_rhba_applicable = fields.Int(allow_none=True)
    advisories_rhea_applicable = fields.Int(allow_none=True)
    advisories_other_applicable = fields.Int(allow_none=True)

    # Advisory counts by type (installable)
    advisories_rhsa_installable = fields.Int(allow_none=True)
    advisories_rhba_installable = fields.Int(allow_none=True)
    advisories_rhea_installable = fields.Int(allow_none=True)
    advisories_other_installable = fields.Int(allow_none=True)

    # Package counts
    packages_applicable = fields.Int(allow_none=True)
    packages_installable = fields.Int(allow_none=True)
    packages_installed = fields.Int(allow_none=True)

    # Template info
    template_name = fields.Str(allow_none=True, validate=marshmallow_validate.Length(max=255))
    template_uuid = fields.UUID(allow_none=True)
