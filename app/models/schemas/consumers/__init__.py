from app.models.schemas.consumers.advisor import AdvisorDataSchema
from app.models.schemas.consumers.compliance import ComplianceDataPolicySchema
from app.models.schemas.consumers.compliance import ComplianceDataSchema
from app.models.schemas.consumers.malware import MalwareDataSchema
from app.models.schemas.consumers.patch import PatchDataSchema
from app.models.schemas.consumers.remediations import RemediationsDataSchema
from app.models.schemas.consumers.vulnerability import VulnerabilityDataSchema

__all__ = [
    "AdvisorDataSchema",
    "ComplianceDataPolicySchema",
    "ComplianceDataSchema",
    "MalwareDataSchema",
    "PatchDataSchema",
    "RemediationsDataSchema",
    "VulnerabilityDataSchema",
]
