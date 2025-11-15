import warnings

from iqe_host_inventory.deprecations import DEPRECATE_MQ_FIXTURES
from iqe_host_inventory.fixtures.kafka_fixtures import *  # noqa: F403

warnings.warn(DEPRECATE_MQ_FIXTURES, stacklevel=2)
