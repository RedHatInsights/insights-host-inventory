"""Marshmallow and request/queue payload schemas (split from a single module for maintainability)."""

# Names kept on the package for tests (patch targets) and queue code.
from jsonschema import validate as jsonschema_validate

from app.models.host import Host
from app.models.host import LimitedHost
from app.models.schemas._log import logger
from app.models.schemas.common import BaseSchemaWithExclude
from app.models.schemas.common import verify_uuid_format_not_empty_dict
from app.models.schemas.consumers import AdvisorDataSchema
from app.models.schemas.consumers import ComplianceDataPolicySchema
from app.models.schemas.consumers import ComplianceDataSchema
from app.models.schemas.consumers import MalwareDataSchema
from app.models.schemas.consumers import PatchDataSchema
from app.models.schemas.consumers import RemediationsDataSchema
from app.models.schemas.consumers import VulnerabilityDataSchema
from app.models.schemas.host import CanonicalFactsSchema
from app.models.schemas.host import FactsSchema
from app.models.schemas.host import HostSchema
from app.models.schemas.host import LimitedHostSchema
from app.models.schemas.host import PatchHostSchema
from app.models.schemas.host import TagsSchema
from app.models.schemas.mq import HostIdListSchema
from app.models.schemas.mq import InputGroupSchema
from app.models.schemas.mq import RequiredHostIdListSchema
from app.models.schemas.outbox import OutboxCreateUpdatePayloadSchema
from app.models.schemas.outbox import OutboxDeletePayloadSchema
from app.models.schemas.outbox import OutboxDeleteReferenceSchema
from app.models.schemas.outbox import OutboxDeleteReporterSchema
from app.models.schemas.outbox import OutboxEventCommonSchema
from app.models.schemas.outbox import OutboxEventMetadataSchema
from app.models.schemas.outbox import OutboxEventReporterSchema
from app.models.schemas.outbox import OutboxEventRepresentationsSchema
from app.models.schemas.outbox import OutboxSchema
from app.models.schemas.staleness import StalenessSchema
from app.models.schemas.system_profile import DiskDeviceSchema
from app.models.schemas.system_profile import DnfModuleSchema
from app.models.schemas.system_profile import HostDynamicSystemProfileSchema
from app.models.schemas.system_profile import HostStaticSystemProfileSchema
from app.models.schemas.system_profile import InstalledProductSchema
from app.models.schemas.system_profile import NetworkInterfaceSchema
from app.models.schemas.system_profile import OperatingSystemSchema
from app.models.schemas.system_profile import RhsmSchema
from app.models.schemas.system_profile import YumRepoSchema
from app.models.schemas.views import InputViewSchema
from app.models.schemas.views import PatchViewSchema
from app.models.schemas.views import ViewResponseSchema

__all__ = [
    "BaseSchemaWithExclude",
    "CanonicalFactsSchema",
    "Host",
    "LimitedHost",
    "jsonschema_validate",
    "verify_uuid_format_not_empty_dict",
    "logger",
    "AdvisorDataSchema",
    "ComplianceDataPolicySchema",
    "ComplianceDataSchema",
    "DiskDeviceSchema",
    "DnfModuleSchema",
    "FactsSchema",
    "HostDynamicSystemProfileSchema",
    "HostIdListSchema",
    "HostSchema",
    "HostStaticSystemProfileSchema",
    "InputGroupSchema",
    "InstalledProductSchema",
    "LimitedHostSchema",
    "MalwareDataSchema",
    "NetworkInterfaceSchema",
    "OperatingSystemSchema",
    "OutboxCreateUpdatePayloadSchema",
    "OutboxDeletePayloadSchema",
    "OutboxDeleteReferenceSchema",
    "OutboxDeleteReporterSchema",
    "OutboxEventCommonSchema",
    "OutboxEventMetadataSchema",
    "OutboxEventReporterSchema",
    "OutboxEventRepresentationsSchema",
    "OutboxSchema",
    "PatchDataSchema",
    "PatchHostSchema",
    "RemediationsDataSchema",
    "RequiredHostIdListSchema",
    "RhsmSchema",
    "StalenessSchema",
    "TagsSchema",
    "VulnerabilityDataSchema",
    "YumRepoSchema",
    "InputViewSchema",
    "PatchViewSchema",
    "ViewResponseSchema",
]
