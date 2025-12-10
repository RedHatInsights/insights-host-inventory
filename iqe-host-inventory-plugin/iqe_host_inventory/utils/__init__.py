from __future__ import annotations

import logging
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Sequence
from datetime import datetime
from datetime import timedelta
from itertools import chain as _chain
from random import randint
from typing import TYPE_CHECKING
from typing import TypeVar

from box import BoxKeyError
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application

if TYPE_CHECKING:
    from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory_api.api.hosts_api import HostsApi as HostsApi

logger = logging.getLogger(__name__)


class InvalidConfigurationParameterError(Exception):
    pass


GLOBAL_ACCOUNTS = ("insights-qa", "insights-qe", "qa@redhat.com")
PRIVATE_ENV_IDENTIFIERS = ("smoke", "ephemeral", "local")

T = TypeVar("T")


def flatten(input: Sequence[Sequence[T]] | Iterator[Sequence[T]]) -> list[T]:
    return [*_chain.from_iterable(input)]


def get_account_number(application: Application, given_account_number: str | None = None) -> str:
    if given_account_number is not None:
        return given_account_number
    try:
        return str(application.user.get("identity").account_number)
    except BoxKeyError:
        raise InvalidConfigurationParameterError(
            "Missing primary_user account_number in your settings.local.yaml file"
        ) from None


def get_org_id(application: Application, given_org_id: str | None = None) -> str:
    if given_org_id is not None:
        return given_org_id

    identity = application.user.get("identity", {})
    org_id = identity.get("org_id") or identity.get("internal", {}).get("org_id")

    if org_id is None:
        raise InvalidConfigurationParameterError(
            "Missing user.identity.org_id or user.identity.internal.org_id field in the config"
        )

    return str(org_id)


def get_username(user_data: DynaBox) -> str:
    username = user_data.get("auth", {}).get("username") or user_data.get("identity", {}).get(
        "user", {}
    ).get("username")
    if username is None:
        raise ValueError(f"Given user doesn't have a defined username: {user_data}")
    return username


def rand_start_end(max_page: int, num_iterations: int) -> tuple[int, int]:
    """

    :param max_page: The highest page of results available (count)
    :param num_iterations: Number of pages to iterate through
    :return:
    """
    random_start = randint(1, max_page)
    if random_start + num_iterations > max_page:
        random_start = 1

    end = random_start + num_iterations
    if end > max_page:
        end = max_page

    return random_start, end


def datetimes_equal(
    datetime1: str | datetime,
    datetime2: str | datetime,
    accuracy: timedelta = timedelta(0),
):
    if isinstance(datetime1, str):
        datetime1 = datetime.fromisoformat(datetime1)
    if isinstance(datetime2, str):
        datetime2 = datetime.fromisoformat(datetime2)
    return abs(datetime1 - datetime2) <= accuracy


def assert_datetimes_equal(
    datetime1: str | datetime,
    datetime2: str | datetime,
    accuracy: timedelta = timedelta(0),
):
    assert datetimes_equal(datetime1, datetime2, accuracy)


def assert_datetimes_mismatch(
    datetime1: str | datetime,
    datetime2: str | datetime,
    accuracy: timedelta = timedelta(0),
):
    assert not datetimes_equal(datetime1, datetime2, accuracy)


def is_global_account(application: Application) -> bool:
    current_env = application.config.current_env.lower()
    is_private_env = any(identifier in current_env for identifier in PRIVATE_ENV_IDENTIFIERS)

    # We don't want to use `get_username` on private envs,
    # some users don't have defined username there.
    if is_private_env:
        return False

    return get_username(application.user).lower() in GLOBAL_ACCOUNTS


def determine_positive_hosts_by_registered_with(
    registered_with: Iterable, hosts: dict[str, HostWrapper]
) -> tuple[set[HostWrapper], set[HostWrapper]]:
    def _is_positive(reporter) -> bool:
        if "yupana" in registered_with and reporter in ("satellite", "discovery"):
            return True
        return reporter in registered_with

    positive_hosts = set()
    negative_hosts = set()

    for rep, host in hosts.items():
        if _is_positive(rep) or rep == "all":
            positive_hosts.add(host)
        else:
            negative_hosts.add(host)

    return positive_hosts, negative_hosts
