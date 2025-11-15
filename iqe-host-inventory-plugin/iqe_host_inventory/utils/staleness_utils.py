from __future__ import annotations

import logging
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Sequence
from datetime import datetime
from datetime import timedelta
from itertools import starmap
from itertools import tee
from random import randint
from random import sample
from time import sleep
from typing import TYPE_CHECKING
from typing import Any
from typing import TypeVar

from iqe_host_inventory.modeling.wrappers import DataAlias
from iqe_host_inventory.utils import assert_datetimes_equal
from iqe_host_inventory_api_v7.models.system_default_id import SystemDefaultId

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory_api.models import HostOut as OldHostOut
from iqe_host_inventory_api_v7.models import HostOut
from iqe_host_inventory_api_v7.models import StalenessOutput

logger = logging.getLogger(__name__)

DAY_SECS = 24 * 60 * 60

MIN_DELTA = 1

type DELTAS = tuple[int, int, int]
type HOSTS_INPUT = list[dict[str, Any]]

TIME_TO_STALE = "conventional_time_to_stale"
TIME_TO_STALE_WARNING = "conventional_time_to_stale_warning"
TIME_TO_DELETE = "conventional_time_to_delete"

STALENESS_FIELDS = (
    TIME_TO_STALE,
    TIME_TO_STALE_WARNING,
    TIME_TO_DELETE,
)


STALENESS_DEFAULTS = {
    TIME_TO_STALE: 104400,
    TIME_TO_STALE_WARNING: 604800,
    TIME_TO_DELETE: 2592000,
}


STALENESS_LIMITS = {
    TIME_TO_STALE: 604800,
    TIME_TO_STALE_WARNING: 15552000,
    TIME_TO_DELETE: 63072000,
}


def get_staleness_defaults() -> dict[str, int]:
    return STALENESS_DEFAULTS


def get_staleness_fields() -> tuple[str, ...]:
    return (*STALENESS_DEFAULTS,)


T = TypeVar("T")


def pairwise(iterable: Iterator[T] | Iterable[T]) -> Iterator[tuple[T, T]]:
    """
    # todo: remove after python3.10
    >>> pairwise('ABCDEFG')
    AB BC CD DE EF FG
    """

    a, b = tee(iterable)
    next(b, None)
    return zip(a, b, strict=False)


def gen_staleness_settings(want_sample: bool = True) -> dict[str, int]:
    """
    Returns a random set of staleness settings. The settings
    will be ordered (within each type) such that:

        staleness < stale_warning < culling

    :param want_sample: return a sampling of the settings
    :return: dict of settings

    Examples:
        gen_staleness_settings()
        gen_staleness_settings(want_sample=False))
    """

    def _gen_settings(fields: Sequence[str]) -> dict[str, int]:
        # Assure ordering when only a portion of the fields are generated
        boundaries = [
            MIN_DELTA,
            STALENESS_DEFAULTS[fields[0]],
            STALENESS_DEFAULTS[fields[1]],
            STALENESS_LIMITS[fields[2]],
        ]
        return dict(zip(fields, starmap(randint, pairwise(boundaries)), strict=False))

    settings = {}

    settings.update(_gen_settings(get_staleness_fields()))

    if want_sample:
        sample_fields = settings.keys()
        settings = {
            f: settings[f] for f in sample(list(sample_fields), randint(1, len(sample_fields)))
        }

    return settings


def extract_staleness_fields(resp: StalenessOutput | dict[str, str | int]) -> dict[str, int]:
    staleness_input = resp if isinstance(resp, dict) else resp.to_dict()
    return {f: staleness_input[f] for f in get_staleness_fields()}  # type: ignore[misc]


def validate_staleness_response(
    resp: dict[str, int], base: dict[str, int], updates: dict[str, int] | None = None
) -> None:
    """
    Helper function that validates staleness api responses.  This would apply
    to apis that return staleness settings.

    :param response: api response
    :param base: expected values if not updated
    :param updates: expected values if there are updates
    :return: None
    """
    if updates is None:
        updates = {}

    for f in get_staleness_fields():
        if f in updates:
            assert resp[f] == updates[f]
        else:
            assert resp[f] == base[f]


def validate_staleness_timestamps(
    last_check_in: str | datetime,
    *,
    stale_timestamp: str | datetime,
    stale_warning_timestamp: str | datetime,
    culled_timestamp: str | datetime,
    staleness_settings: dict[str, int] | None = None,
) -> None:
    """Validate staleness timestamps compared to 'last_check_in' timestamp. This can be used for
    validating host level staleness as well as per reporter staleness."""
    staleness_settings = staleness_settings or get_staleness_defaults()
    staleness_deltas = {
        "stale": staleness_settings[TIME_TO_STALE],
        "stale_warning": staleness_settings[TIME_TO_STALE_WARNING],
        "culled": staleness_settings[TIME_TO_DELETE],
    }

    last_check_in = (
        datetime.fromisoformat(last_check_in) if isinstance(last_check_in, str) else last_check_in
    )

    assert_datetimes_equal(
        stale_timestamp, last_check_in + timedelta(seconds=staleness_deltas["stale"])
    )
    assert_datetimes_equal(
        stale_warning_timestamp,
        last_check_in + timedelta(seconds=staleness_deltas["stale_warning"]),
    )
    assert_datetimes_equal(
        culled_timestamp, last_check_in + timedelta(seconds=staleness_deltas["culled"])
    )


def validate_host_timestamps(
    host_inventory_app: ApplicationHostInventory,
    # TODO: phase out hostout variants
    host: HostWrapper | HostOut | OldHostOut,
    host_type: str = "conventional",
) -> None:
    """
    Helper function that validates host staleness timestamps.  The host's
    system profile contains the host type, but only for edge hosts and I
    think that's only because we set it.  For now, require the caller to
    pass in the host type.

    :param host_inventory_app: application object
    :param host: host object
    :param host_type: "conventional" (default) or "edge"
    :return None
    """
    if not isinstance(host, HostWrapper):
        host = HostWrapper(host.to_dict())

    settings = host_inventory_app.apis.account_staleness.get_staleness()
    logger.info(f"Staleness settings:\n{settings}")

    logger.info(f"Host type: {host_type}")
    logger.info(f"Host last_check_in: {host.last_check_in}")
    logger.info(f"Host stale timestamp: {host.stale_timestamp}")
    logger.info(f"Host stale warning timestamp: {host.stale_warning_timestamp}")
    logger.info(f"Host culled timestamp: {host.culled_timestamp}")

    validate_staleness_timestamps(
        host.last_check_in,
        stale_timestamp=host.stale_timestamp,
        stale_warning_timestamp=host.stale_warning_timestamp,
        culled_timestamp=host.culled_timestamp,
        staleness_settings=settings,
    )


def set_staleness(host_inventory: ApplicationHostInventory, deltas: DELTAS) -> None:
    """
    Helper function that creates/updates a custom staleness record given
    a list of ordered deltas as defined below.

    :param deltas: [staleness_delta, stale_warning delta, culling_delta]
    :return: None
    """
    settings = dict(zip(get_staleness_fields(), deltas, strict=False))

    resp = host_inventory.apis.account_staleness.get_staleness_response()
    # TODO remove openapi codegen indirection
    if resp.id.actual_instance == SystemDefaultId.SYSTEM_DEFAULT:
        host_inventory.apis.account_staleness.create_staleness(**settings)
    else:
        host_inventory.apis.account_staleness.update_staleness(**settings)


def create_hosts_in_state(
    host_inventory: ApplicationHostInventory,
    hosts_data: HOSTS_INPUT,
    host_state: str,
    *,
    host_type: str = "conventional",
    deltas: DELTAS | None = None,
    cleanup_scope: str = "function",
) -> list[HostWrapper]:
    # TODO: Check if we can switch to 3 seconds now that xjoin is removed
    # If we set the culling delta too small, host creation/retrieval
    # can fail.  10 seconds seems to suffice.
    default_deltas = {
        "stale": (1, 3600, 7200),
        "stale_warning": (1, 2, 7200),
        "culling": (1, 2, 3),
    }

    indices = {
        "stale": 0,
        "stale_warning": 1,
        "culling": 2,
    }

    # For fresh hosts, the default settings are fine
    delay = 0
    if host_state != "fresh":
        if deltas is None:
            deltas = default_deltas[host_state]
        set_staleness(host_inventory, deltas)
        delay = deltas[indices[host_state]]

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data, cleanup_scope=cleanup_scope)
    for host in hosts:
        retrieved_host = host_inventory.apis.hosts.get_host_by_id(host.id)
        if host.reporter != "rhsm-system-profile-bridge":
            validate_host_timestamps(
                host_inventory, HostWrapper(retrieved_host.to_dict()), host_type
            )

    if delay:
        logger.info(f"Waiting {delay} second(s) for host(s) to become {host_state}")
        sleep(delay)

    return hosts


def create_hosts_fresh_stale(
    host_inventory: ApplicationHostInventory,
    fresh_hosts_data: HOSTS_INPUT,
    stale_hosts_data: HOSTS_INPUT,
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (5, 10, 15),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    stale_hosts = create_hosts_in_state(
        host_inventory,
        hosts_data=stale_hosts_data,
        host_state="stale",
        host_type=host_type,
        deltas=deltas,
        cleanup_scope=cleanup_scope,
    )

    fresh_hosts = host_inventory.kafka.create_hosts(
        hosts_data=fresh_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )
    return {"fresh": fresh_hosts, "stale": stale_hosts}


def create_hosts_fresh_stalewarning(
    host_inventory: ApplicationHostInventory,
    fresh_hosts_data: HOSTS_INPUT,
    stale_warning_hosts_data: HOSTS_INPUT,
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (5, 10, 15),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    stale_warning_hosts = create_hosts_in_state(
        host_inventory,
        hosts_data=stale_warning_hosts_data,
        host_state="stale_warning",
        host_type=host_type,
        deltas=deltas,
        cleanup_scope=cleanup_scope,
    )

    fresh_hosts = host_inventory.kafka.create_hosts(
        hosts_data=fresh_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )
    return {"fresh": fresh_hosts, "stale_warning": stale_warning_hosts}


def create_hosts_fresh_culled(
    host_inventory: ApplicationHostInventory,
    fresh_hosts_data: list[dict],
    culled_hosts_data: list[dict],
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (5, 10, 15),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    culled_hosts = create_hosts_in_state(
        host_inventory,
        hosts_data=culled_hosts_data,
        host_state="culling",
        host_type=host_type,
        deltas=deltas,
        cleanup_scope=cleanup_scope,
    )

    fresh_hosts = host_inventory.kafka.create_hosts(
        hosts_data=fresh_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )
    return {"fresh": fresh_hosts, "culled": culled_hosts}


def create_hosts_stale_stalewarning(
    host_inventory: ApplicationHostInventory,
    stale_hosts_data: list[dict],
    stale_warning_hosts_data: list[dict],
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (5, 10, 15),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    hosts = create_hosts_fresh_stale(
        host_inventory,
        fresh_hosts_data=stale_hosts_data,
        stale_hosts_data=stale_warning_hosts_data,
        host_type=host_type,
        deltas=deltas,
        field_to_match=field_to_match,
        cleanup_scope=cleanup_scope,
    )
    logger.info(
        f"Waiting {deltas[0]} second(s) for host(s) to reach stale and stale_warning states"
    )
    sleep(deltas[0])

    return {"stale": hosts["fresh"], "stale_warning": hosts["stale"]}


def create_hosts_stale_culled(
    host_inventory: ApplicationHostInventory,
    stale_hosts_data: HOSTS_INPUT,
    culled_hosts_data: HOSTS_INPUT,
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (5, 10, 15),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    hosts = create_hosts_fresh_stalewarning(
        host_inventory,
        fresh_hosts_data=stale_hosts_data,
        stale_warning_hosts_data=culled_hosts_data,
        host_type=host_type,
        deltas=deltas,
        field_to_match=field_to_match,
        cleanup_scope=cleanup_scope,
    )
    logger.info(f"Waiting {deltas[0]} second(s) for host(s) to reach stale and culled states")
    sleep(deltas[0])

    return {"stale": hosts["fresh"], "culled": hosts["stale_warning"]}


def create_hosts_stalewarning_culled(
    host_inventory: ApplicationHostInventory,
    stale_warning_hosts_data: list[dict],
    culled_hosts_data: list[dict],
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (5, 10, 15),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    hosts = create_hosts_stale_stalewarning(
        host_inventory,
        stale_hosts_data=stale_warning_hosts_data,
        stale_warning_hosts_data=culled_hosts_data,
        host_type=host_type,
        deltas=deltas,
        field_to_match=field_to_match,
        cleanup_scope=cleanup_scope,
    )
    logger.info(
        f"Waiting {deltas[0]} second(s) for host(s) to reach stale_warning and culled states"
    )
    sleep(deltas[0])

    return {"stale_warning": hosts["stale"], "culled": hosts["stale_warning"]}


def create_hosts_fresh_stale_stalewarning(
    host_inventory: ApplicationHostInventory,
    fresh_hosts_data: list[dict],
    stale_hosts_data: list[dict],
    stale_warning_hosts_data: list[dict],
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (10, 20, 30),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    hosts = create_hosts_fresh_stale(
        host_inventory,
        fresh_hosts_data=stale_hosts_data,
        stale_hosts_data=stale_warning_hosts_data,
        host_type=host_type,
        deltas=deltas,
        field_to_match=field_to_match,
        cleanup_scope=cleanup_scope,
    )
    logger.info(
        f"Waiting {deltas[0]} second(s) for host(s) to reach stale and stale_warning states"
    )
    sleep(deltas[0])

    fresh_hosts = host_inventory.kafka.create_hosts(
        hosts_data=fresh_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )
    return {"fresh": fresh_hosts, "stale": hosts["fresh"], "stale_warning": hosts["stale"]}


def create_hosts_fresh_stale_culled(
    host_inventory: ApplicationHostInventory,
    fresh_hosts_data: list[dict],
    stale_hosts_data: list[dict],
    culled_hosts_data: list[dict],
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (10, 20, 30),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    culled_hosts = create_hosts_in_state(
        host_inventory,
        hosts_data=culled_hosts_data,
        host_state="stale_warning",
        host_type=host_type,
        deltas=deltas,
        cleanup_scope=cleanup_scope,
    )

    stale_hosts = host_inventory.kafka.create_hosts(
        hosts_data=stale_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )

    logger.info(f"Waiting {deltas[0]} second(s) for host(s) to reach stale and culled states")
    sleep(deltas[0])

    fresh_hosts = host_inventory.kafka.create_hosts(
        hosts_data=fresh_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )
    return {"fresh": fresh_hosts, "stale": stale_hosts, "culled": culled_hosts}


def create_hosts_fresh_stalewarning_culled(
    host_inventory: ApplicationHostInventory,
    fresh_hosts_data: HOSTS_INPUT,
    stale_warning_hosts_data: HOSTS_INPUT,
    culled_hosts_data: HOSTS_INPUT,
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (10, 20, 30),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    culled_hosts = create_hosts_in_state(
        host_inventory,
        hosts_data=culled_hosts_data,
        host_state="stale",
        host_type=host_type,
        deltas=deltas,
        cleanup_scope=cleanup_scope,
    )

    stale_warning_hosts = host_inventory.kafka.create_hosts(
        hosts_data=stale_warning_hosts_data,
        field_to_match=field_to_match,
        cleanup_scope=cleanup_scope,
    )

    logger.info(
        f"Waiting {deltas[0]} second(s) for host(s) to reach stale_warning and culled states"
    )
    sleep(deltas[0] * 2)

    fresh_hosts = host_inventory.kafka.create_hosts(
        hosts_data=fresh_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )
    return {"fresh": fresh_hosts, "stale_warning": stale_warning_hosts, "culled": culled_hosts}


def create_hosts_stale_stalewarning_culled(
    host_inventory: ApplicationHostInventory,
    stale_hosts_data: HOSTS_INPUT,
    stale_warning_hosts_data: HOSTS_INPUT,
    culled_hosts_data: HOSTS_INPUT,
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (10, 20, 30),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    culled_hosts = create_hosts_in_state(
        host_inventory,
        hosts_data=culled_hosts_data,
        host_state="stale",
        host_type=host_type,
        deltas=deltas,
        cleanup_scope=cleanup_scope,
    )

    stale_warning_hosts = host_inventory.kafka.create_hosts(
        hosts_data=stale_warning_hosts_data,
        field_to_match=field_to_match,
        cleanup_scope=cleanup_scope,
    )

    logger.info(
        f"Waiting {deltas[0]} second(s) for host(s) to reach stale and stale_warning states"
    )
    sleep(deltas[0])

    stale_hosts = host_inventory.kafka.create_hosts(
        hosts_data=stale_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )

    logger.info(
        f"Waiting {deltas[0]} second(s) for host(s) to reach stale, stale_warning, and culled states"  # noqa
    )
    sleep(deltas[0])

    return {"stale": stale_hosts, "stale_warning": stale_warning_hosts, "culled": culled_hosts}


def create_hosts_fresh_stale_stalewarning_culled(
    host_inventory: ApplicationHostInventory,
    fresh_hosts_data: HOSTS_INPUT,
    stale_hosts_data: HOSTS_INPUT,
    stale_warning_hosts_data: HOSTS_INPUT,
    culled_hosts_data: HOSTS_INPUT,
    *,
    host_type: str = "conventional",
    deltas: DELTAS = (10, 20, 30),
    field_to_match: DataAlias = HostWrapper.insights_id,
    cleanup_scope: str = "function",
) -> dict[str, list[HostWrapper]]:
    hosts = create_hosts_stale_stalewarning_culled(
        host_inventory,
        stale_hosts_data=stale_hosts_data,
        stale_warning_hosts_data=stale_warning_hosts_data,
        culled_hosts_data=culled_hosts_data,
        host_type=host_type,
        deltas=deltas,
        field_to_match=field_to_match,
        cleanup_scope=cleanup_scope,
    )
    fresh_hosts = host_inventory.kafka.create_hosts(
        hosts_data=fresh_hosts_data, field_to_match=field_to_match, cleanup_scope=cleanup_scope
    )
    return {
        "fresh": fresh_hosts,
        "stale": hosts["stale"],
        "stale_warning": hosts["stale_warning"],
        "culled": hosts["culled"],
    }
