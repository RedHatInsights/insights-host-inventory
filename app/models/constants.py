import os
from datetime import UTC
from datetime import datetime
from enum import Enum

from marshmallow import validate as marshmallow_validate

TAG_NAMESPACE_VALIDATION = marshmallow_validate.Length(max=255)
TAG_KEY_VALIDATION = marshmallow_validate.Length(min=1, max=255)
TAG_VALUE_VALIDATION = marshmallow_validate.Length(max=255)

SPECIFICATION_DIR = "./swagger/"
SYSTEM_PROFILE_SPECIFICATION_FILE = "system_profile.spec.yaml"

FAR_FUTURE_STALE_TIMESTAMP = datetime(2260, 1, 1, tzinfo=UTC)

NEW_TO_OLD_REPORTER_MAP = {"satellite": "yupana", "discovery": "yupana"}
OLD_TO_NEW_REPORTER_MAP = {"yupana": ("satellite", "discovery")}

MIN_CANONICAL_FACTS_VERSION = 0
MAX_CANONICAL_FACTS_VERSION = 1

ZERO_MAC_ADDRESS = "00:00:00:00:00:00"

INVENTORY_SCHEMA = os.getenv("INVENTORY_DB_SCHEMA", "hbi")


class ProviderType(str, Enum):
    ALIBABA = "alibaba"
    AWS = "aws"
    AZURE = "azure"
    DISCOVERY = "discovery"
    GCP = "gcp"
    IBM = "ibm"


class SystemType(str, Enum):
    CONVENTIONAL = "conventional"
    BOOTC = "bootc"
    EDGE = "edge"
