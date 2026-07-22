import warnings

from iqe_host_inventory.deprecations import DEPRECATE_MQ_FIXTURES
from iqe_host_inventory.fixtures.kafka_fixtures import *  # ruff:ignore[undefined-local-with-import-star]

warnings.warn(DEPRECATE_MQ_FIXTURES, stacklevel=2)
