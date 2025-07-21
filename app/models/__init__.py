from datetime import datetime

from jsonschema import validate as jsonschema_validate

from app.logging import get_logger
from app.models.constants import EDGE_HOST_STALE_TIMESTAMP
from app.models.constants import INVENTORY_SCHEMA
from app.models.constants import MAX_CANONICAL_FACTS_VERSION
from app.models.constants import MIN_CANONICAL_FACTS_VERSION
from app.models.constants import NEW_TO_OLD_REPORTER_MAP
from app.models.constants import OLD_TO_NEW_REPORTER_MAP
from app.models.constants import SPECIFICATION_DIR
from app.models.constants import SYSTEM_PROFILE_SPECIFICATION_FILE
from app.models.constants import TAG_KEY_VALIDATION
from app.models.constants import TAG_NAMESPACE_VALIDATION
from app.models.constants import TAG_VALUE_VALIDATION
from app.models.constants import ZERO_MAC_ADDRESS
from app.models.constants import ProviderType
from app.models.database import db
from app.models.database import migrate
from app.models.group import Group
from app.models.host import Host
from app.models.host import LimitedHost
from app.models.host_group_assoc import HostGroupAssoc
from app.models.outbox import Outbox
from app.models.host_inventory_metadata import HostInventoryMetadata
from app.models.schemas import CanonicalFactsSchema
from app.models.schemas import DiskDeviceSchema
from app.models.schemas import DnfModuleSchema
from app.models.schemas import FactsSchema
from app.models.schemas import HostSchema
from app.models.schemas import InputGroupSchema
from app.models.schemas import InstalledProductSchema
from app.models.schemas import LimitedHostSchema
from app.models.schemas import NetworkInterfaceSchema
from app.models.schemas import OperatingSystemSchema
from app.models.schemas import PatchHostSchema
from app.models.schemas import RhsmSchema
from app.models.schemas import StalenessSchema
from app.models.schemas import TagsSchema
from app.models.schemas import YumRepoSchema
from app.models.staleness import Staleness
from app.models.system_profile_normalizer import SystemProfileNormalizer
from app.models.utils import _create_staleness_timestamps_values
from app.models.utils import _get_staleness_obj
from app.models.utils import _set_display_name_on_save
from app.models.utils import _time_now
from app.models.utils import deleted_by_this_query
from lib.feature_flags import get_flag_value

logger = get_logger(__name__)

__all__ = [
    "db",
    "migrate",
    "get_flag_value",
    "jsonschema_validate",
    "logger",
    "ProviderType",
    "TAG_NAMESPACE_VALIDATION",
    "TAG_KEY_VALIDATION",
    "TAG_VALUE_VALIDATION",
    "SPECIFICATION_DIR",
    "SYSTEM_PROFILE_SPECIFICATION_FILE",
    "EDGE_HOST_STALE_TIMESTAMP",
    "NEW_TO_OLD_REPORTER_MAP",
    "OLD_TO_NEW_REPORTER_MAP",
    "MIN_CANONICAL_FACTS_VERSION",
    "MAX_CANONICAL_FACTS_VERSION",
    "ZERO_MAC_ADDRESS",
    "INVENTORY_SCHEMA",
    "SystemProfileNormalizer",
    "LimitedHost",
    "Host",
    "Group",
    "HostGroupAssoc",
    "Outbox",
    "Staleness",
    "HostInventoryMetadata",
    "DiskDeviceSchema",
    "RhsmSchema",
    "OperatingSystemSchema",
    "YumRepoSchema",
    "DnfModuleSchema",
    "InstalledProductSchema",
    "NetworkInterfaceSchema",
    "FactsSchema",
    "TagsSchema",
    "CanonicalFactsSchema",
    "LimitedHostSchema",
    "HostSchema",
    "PatchHostSchema",
    "InputGroupSchema",
    "StalenessSchema",
    "_get_staleness_obj",
    "_set_display_name_on_save",
    "_time_now",
    "_create_staleness_timestamps_values",
    "deleted_by_this_query",
    "datetime",
]
