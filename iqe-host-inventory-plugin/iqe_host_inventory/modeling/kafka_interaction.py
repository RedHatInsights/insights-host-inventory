# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import warnings
from collections.abc import Iterator
from copy import deepcopy
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any
from typing import TypeVar
from typing import cast

import attr
import pytest
from confluent_kafka import Message
from dynaconf.utils.boxing import DynaBox
from iqe.base.modeling import BaseEntity
from iqe_mq._kafka_consumer import IQEKafkaConsumer
from iqe_mq._kafka_producer import IQEKafkaProducer

from iqe_host_inventory.deprecations import DEPRECATE_MAKE_HOST_DATA
from iqe_host_inventory.deprecations import DEPRECATE_MAKE_HOST_EVENTS
from iqe_host_inventory.deprecations import DEPRECATE_PRODUCE_HOST_UPDATE_MESSAGES
from iqe_host_inventory.modeling.wrappers import HOST_DATA_OUT
from iqe_host_inventory.modeling.wrappers import BaseNotificationWrapper
from iqe_host_inventory.modeling.wrappers import DataAlias
from iqe_host_inventory.modeling.wrappers import DeleteNotificationWrapper
from iqe_host_inventory.modeling.wrappers import ErrorNotificationWrapper
from iqe_host_inventory.modeling.wrappers import HostMessageWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.modeling.wrappers import RegisteredNotificationWrapper
from iqe_host_inventory.modeling.wrappers import StaleNotificationWrapper
from iqe_host_inventory.utils import get_account_number
from iqe_host_inventory.utils import get_org_id
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import create_host_data
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import generate_complete_random_host
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_minimal_host
from iqe_host_inventory.utils.datagen_utils import generate_tags
from iqe_host_inventory.utils.datagen_utils import get_clamped_timestamp
from iqe_host_inventory.utils.kafka_utils import wrap_payload

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory


T = TypeVar(
    "T",
    HostMessageWrapper,
    BaseNotificationWrapper,
    ErrorNotificationWrapper,
    DeleteNotificationWrapper,
    RegisteredNotificationWrapper,
    StaleNotificationWrapper,
)

SAP_FILTER_DISPLAY_NAME = ".HBI-FILTER-TEST"
SAP_FILTER_TAG = "hbi-filter-test"


@attr.s
class HBIKafkaDatagen(BaseEntity):
    def make_host_data(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        warnings.warn(DEPRECATE_MAKE_HOST_DATA, stacklevel=2)
        if "extra_data" in kwargs:
            extra_data = kwargs.pop("extra_data")
            return self.create_host_data(*args, **kwargs, **extra_data)
        return self.create_host_data(*args, **kwargs)

    def create_host_data(
        self,
        *,
        org_id: str | None = None,
        account_number: str | None = None,
        host_type: str | None = None,
        include_sp: bool = True,
        name_prefix: str = "rhiqe",
        **extra_data: Any,
    ) -> dict[str, Any]:
        """Create a host data that will match the supported 'data' structure from here:
        https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
        The 'host_type' parameter will set the system_profile.host_type value.
        The 'name_prefix' parameter will set the prefix for display_name and fqdn.
        Any other host fields (on the root level) can be adjusted by keyword arguments.
        """
        org_id = get_org_id(self.application, given_org_id=org_id)
        account_number = get_account_number(self.application, given_account_number=account_number)
        return create_host_data(
            account_number=account_number,
            org_id=org_id,
            host_type=host_type,
            include_sp=include_sp,
            name_prefix=name_prefix,
            **extra_data,
        )

    def create_n_hosts_data(
        self,
        n: int,
        *,
        org_id: str | None = None,
        account_number: str | None = None,
        host_type: str | None = None,
        include_sp: bool = True,
        name_prefix: str = "rhiqe",
        **extra_data: Any,
    ) -> list[dict[str, Any]]:
        return [
            self.create_host_data(
                account_number=account_number,
                org_id=org_id,
                host_type=host_type,
                include_sp=include_sp,
                name_prefix=name_prefix,
                **extra_data,
            )
            for _ in range(n)
        ]

    def create_host_data_with_tags(
        self,
        *,
        org_id: str | None = None,
        account_number: str | None = None,
        host_type: str | None = None,
        include_sp: bool = True,
        name_prefix: str = "rhiqe",
        tags: list[TagDict] | None = None,
        **extra_data: Any,
    ) -> dict[str, Any]:
        """Create a host data that will match the supported 'data' structure from here:
        https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
        The tags will be automatically generated, if not provided.
        The 'host_type' parameter will set the system_profile.host_type value.
        The 'name_prefix' parameter will set the prefix for display_name and fqdn.
        Any other host fields (on the root level) can be adjusted by keyword arguments.
        """
        return self.create_host_data(
            account_number=account_number,
            org_id=org_id,
            host_type=host_type,
            include_sp=include_sp,
            name_prefix=name_prefix,
            tags=tags or generate_tags(),
            **extra_data,
        )

    def create_n_hosts_data_with_tags(
        self,
        n: int,
        *,
        org_id: str | None = None,
        account_number: str | None = None,
        host_type: str | None = None,
        include_sp: bool = True,
        name_prefix: str = "rhiqe",
        tags: list[TagDict] | None = None,
        **extra_data: Any,
    ) -> list[dict[str, Any]]:
        return [
            self.create_host_data_with_tags(
                account_number=account_number,
                org_id=org_id,
                host_type=host_type,
                include_sp=include_sp,
                name_prefix=name_prefix,
                tags=tags,
                **extra_data,
            )
            for _ in range(n)
        ]

    def create_host_data_for_sap_filtering(self) -> dict[str, Any]:
        return self.create_host_data(
            tags=[gen_tag(namespace=SAP_FILTER_TAG)],
            display_name=generate_display_name() + SAP_FILTER_DISPLAY_NAME,
        )

    def create_hosts_data_for_reporter_filtering(
        self, reporter_prefix: str
    ) -> list[dict[str, Any]]:
        host = self.create_host_data(
            include_sp=False,
            reporter=reporter_prefix,
            stale_timestamp=get_clamped_timestamp("+20m"),
        )

        host_update = {
            **host,
            "reporter": f"{reporter_prefix}_other",
            "stale_timestamp": get_clamped_timestamp("+40m"),
        }

        return [host, host_update]

    def create_complete_host_data(
        self,
        *,
        org_id: str | None = None,
        account_number: str | None = None,
        display_name_prefix: str = "rhiqe",
        include_sp: bool = True,
        is_virtual: bool = True,
        is_sap_system: bool = False,
        is_edge: bool = False,
        is_image_mode: bool = False,
    ) -> dict[str, Any]:
        """
        Create a host_data dictionary with all host fields populated.
        If `is_virtual` is set to False, `provider_id` and `provider_type` fields will be missing.
        If `include_sp` is set to True, then the system_profile will be fully populated too,
        otherwise the system_profile will be missing.
        By default, the system_profile will have all fields populated except of all the SAP fields,
        the `host_type` and the `bootc_status` fields. For these to be populated you have to set
        `is_sap_system`, `is_edge` and `is_image_mode` parameters to True respectively.
        """
        org_id = get_org_id(self.application, given_org_id=org_id)
        account_number = get_account_number(self.application, given_account_number=account_number)
        return generate_complete_random_host(
            org_id,
            account_number=account_number,
            display_name_prefix=display_name_prefix,
            include_sp=include_sp,
            is_virtual=is_virtual,
            is_sap_system=is_sap_system,
            is_edge=is_edge,
            is_image_mode=is_image_mode,
        )

    def create_n_complete_hosts_data(
        self,
        n: int,
        *,
        org_id: str | None = None,
        account_number: str | None = None,
        display_name_prefix: str = "rhiqe",
        include_sp: bool = True,
        is_virtual: bool = True,
        is_sap_system: bool = False,
        is_edge: bool = False,
        is_image_mode: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            self.create_complete_host_data(
                org_id=org_id,
                account_number=account_number,
                display_name_prefix=display_name_prefix,
                include_sp=include_sp,
                is_virtual=is_virtual,
                is_sap_system=is_sap_system,
                is_edge=is_edge,
                is_image_mode=is_image_mode,
            )
            for _ in range(n)
        ]

    def create_minimal_host_data(
        self, *, org_id: str | None = None, **extra_fields: Any
    ) -> dict[str, Any]:
        """
        Create a host_data dictionary with a minimal set of fields required by HBI.
        This includes all the required fields (which you can check in `datagen_utils.py`, currently
        `org_id`, `provider` and `stale_timestamp`) + 1 canonical fact. If you don't provide
        any canonical fact in the `extra_fields`, the `insights_id` will be included.
        """
        org_id = get_org_id(self.application, given_org_id=org_id)
        return generate_minimal_host(org_id, **extra_fields)

    def create_n_minimal_hosts_data(
        self, n: int, *, org_id: str | None = None, **extra_fields: Any
    ) -> list[dict[str, Any]]:
        return [self.create_minimal_host_data(org_id=org_id, **extra_fields) for _ in range(n)]


def _find_host_by_field(
    host_messages: list[HostMessageWrapper], field: DataAlias, value: Any
) -> HostWrapper:
    if field.name is None:
        # This should never happen, I need it for mypy to be happy
        raise ValueError("This field doesn't have a name")

    matching_hosts = [
        host_msg.host for host_msg in host_messages if getattr(host_msg.host, field.name) == value
    ]

    if len(matching_hosts) != 1:
        raise ValueError(
            f"Expected exactly one matching host message with {field.name} == {value}, "
            f"found {len(matching_hosts)}"
        )

    return matching_hosts[0]


def _sort_created_hosts(
    hosts_data: list[dict[str, Any]],
    host_msgs: list[HostMessageWrapper],
    field_to_match: DataAlias,
) -> list[HostWrapper]:
    if field_to_match.name is None:
        # This should never happen, I need it for mypy to be happy
        raise ValueError("This field doesn't have a name")

    created_hosts = []
    for host_data in hosts_data:
        created_hosts.append(
            _find_host_by_field(host_msgs, field_to_match, host_data[field_to_match.name])
        )

    return created_hosts


@attr.s
class HBIKafkaActions(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def _datagen(self) -> HBIKafkaDatagen:
        return self._host_inventory.datagen

    @cached_property
    def _kafka_config(self) -> DynaBox:
        return self._host_inventory.config.kafka

    @cached_property
    def _events_wait_time(self) -> int:
        return int(self._kafka_config.events_timeout)

    @cached_property
    def _consumer(self) -> IQEKafkaConsumer:
        consumer = self.application.mq.get_consumer_for_plugin(self._host_inventory)
        consumer.subscribe([self.events_topic, self.notifications_topic])
        # flush hack
        # Unfortunately, the mini_drain doesn't work: https://issues.redhat.com/browse/IQE-3555
        consumer.mini_drain()
        return consumer

    @cached_property
    def _producer(self) -> IQEKafkaProducer:
        return self.application.mq.producer

    @cached_property
    def ingress_topic(self) -> str:
        return self._kafka_config.ingress_topic

    @cached_property
    def system_profile_topic(self) -> str:
        return self._kafka_config.system_profile_topic

    @cached_property
    def notifications_topic(self) -> str:
        return self._kafka_config.notifications_topic

    @cached_property
    def events_topic(self) -> str:
        return self._kafka_config.events_topic

    @cached_property
    def identity(self) -> dict:
        return self.application.user.identity

    def _produce_host_messages(
        self,
        hosts_data: list[dict[str, Any]],
        *,
        operation: str,
        topic: str,
        metadata: dict | None = None,
        operation_args: dict[str, str] | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        flush: bool = True,
        quiet: bool = False,
        key: str | None = None,
    ) -> None:
        # Unfortunately, the mini_drain doesn't work: https://issues.redhat.com/browse/IQE-3555
        self._consumer.mini_drain()  # ensure we drain

        for host_data in hosts_data:
            host_message = wrap_payload(
                host_data,
                identity=self.identity,
                operation=operation,
                metadata=metadata,
                operation_args=operation_args,
                omit_identity=omit_identity,
                omit_metadata=omit_metadata,
                omit_request_id=omit_request_id,
            )
            self._producer.produce(
                topic,
                host_message,
                key=key,
            )
            if not quiet:
                log.info(f"Produced message: {host_message}")
        if flush:
            res = self._producer.flush(timeout=15)
            log.info(f"flush completed, {res} still in queue")

    def produce_host_update_messages(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn(DEPRECATE_PRODUCE_HOST_UPDATE_MESSAGES, stacklevel=2)
        self.produce_host_create_messages(*args, **kwargs)

    def produce_host_create_messages(
        self,
        hosts_data: list[dict[str, Any]],
        *,
        metadata: dict | None = None,
        operation_args: dict | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        flush: bool = True,
        quiet: bool = False,
        key: str | None = None,
    ) -> None:
        """Send host create kafka messages to platform.inventory.host-ingress topic.

        :param list[dict[str, Any]] hosts_data: (Required) List of host data to be used for hosts
            creation. The data should have a structure that is accepted by HBI. More info here:
            https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
        :param dict metadata: Used to pass data associated with the host from the ingress service
            to the backend applications (request_id, identity, S3 bucket URL, etc.).
            If not provided, correct identity and a random request_id will be generated.
        :param dict operation_args: Arguments that are passed to the operation. The only supported
            argument right now is 'defer_to_reporter'.
            No operation_args will be used by default.
        :param bool omit_metadata: If true, metadata will not be generated.
            Default: False
        :param bool omit_identity: If true, identity will not be generated.
            Default: False
        :param bool omit_request_id: If true, request_id will not be generated.
            Default: False
        :param bool flush: If true, messages will be flushed immediately.
            Default: True
        :param bool quiet: If true, the produced host messages will not be logged.
            Default: False
        :param str key: This will be used as a key for the produced kafka host messages.
            Default: None
        :return None
        """
        self._produce_host_messages(
            hosts_data,
            operation="add_host",
            topic=self.ingress_topic,
            metadata=metadata,
            operation_args=operation_args,
            omit_metadata=omit_metadata,
            omit_identity=omit_identity,
            omit_request_id=omit_request_id,
            flush=flush,
            quiet=quiet,
            key=key,
        )

    def produce_sp_update_messages(
        self,
        hosts_data: list[dict[str, Any]],
        *,
        metadata: dict | None = None,
        operation_args: dict | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        flush: bool = True,
        quiet: bool = False,
        key: str | None = None,
    ) -> None:
        """Send system_profile update kafka messages to platform.inventory.system_profile topic.

        :param list[dict[str, Any]] hosts_data: (Required) List of host data to be used for hosts
            updates. The data should have a structure that is accepted by HBI. More info here:
            https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
        :param dict metadata: Used to pass data associated with the host from the ingress service
            to the backend applications (request_id, identity, S3 bucket URL, etc.).
            If not provided, correct identity and a random request_id will be generated.
        :param dict operation_args: Arguments that are passed to the operation. The only supported
            argument right now is 'defer_to_reporter'.
            No operation_args will be used by default.
        :param bool omit_metadata: If true, metadata will not be generated.
            Default: False
        :param bool omit_identity: If true, identity will not be generated.
            Default: False
        :param bool omit_request_id: If true, request_id will not be generated.
            Default: False
        :param bool flush: If true, messages will be flushed immediately.
            Default: True
        :param bool quiet: If true, the produced host messages will not be logged.
            Default: False
        :param str key: This will be used as a key for the produced kafka system_profile messages.
            Default: None
        :return None
        """
        self._produce_host_messages(
            hosts_data,
            operation="update_system_profile",
            topic=self.system_profile_topic,
            metadata=metadata,
            operation_args=operation_args,
            omit_metadata=omit_metadata,
            omit_identity=omit_identity,
            omit_request_id=omit_request_id,
            flush=flush,
            quiet=quiet,
            key=key,
        )

    def _walk_events(self, *, timeout: int) -> Iterator[Message]:
        yield from self._consumer.walk_messages(timeout=timeout, wrap=False)

    def _walk_events_with_wrappers(
        self, *, timeout: int
    ) -> Iterator[
        Message
        | HostMessageWrapper
        | BaseNotificationWrapper
        | ErrorNotificationWrapper
        | DeleteNotificationWrapper
        | RegisteredNotificationWrapper
        | StaleNotificationWrapper
    ]:
        for message in self._walk_events(timeout=timeout):
            if message.topic() == self.events_topic:
                yield HostMessageWrapper.from_message(message)
            elif (
                message.topic() == self.notifications_topic
                # observed 'source': 'urn:redhat:source:console:app:repositories'
                # after image_builder usage
                and message.value().get("application")
                == "inventory"  # Other apps use the same topic
            ):
                if message.value()["event_type"] == "validation-error":
                    yield ErrorNotificationWrapper.from_message(message)
                elif message.value()["event_type"] == "system-deleted":
                    yield DeleteNotificationWrapper.from_message(message)
                elif message.value()["event_type"] == "new-system-registered":
                    yield RegisteredNotificationWrapper.from_message(message)
                elif message.value()["event_type"] == "system-became-stale":
                    yield StaleNotificationWrapper.from_message(message)
                else:
                    yield BaseNotificationWrapper.from_message(message)
            else:
                yield message

    def walk_messages(
        self, *, timeout: int | None = None
    ) -> Iterator[
        Message
        | HostMessageWrapper
        | BaseNotificationWrapper
        | ErrorNotificationWrapper
        | DeleteNotificationWrapper
        | RegisteredNotificationWrapper
        | StaleNotificationWrapper
    ]:
        yield from self._walk_events_with_wrappers(timeout=timeout or self._events_wait_time)

    def _walk_messages(
        self, requested_type: type[T] | tuple[type[T], ...], *, timeout: int | None = None
    ) -> Iterator[T]:
        for message in self.walk_messages(timeout=timeout):
            if isinstance(message, requested_type):
                yield cast(T, message)

    def _walk_messages_with_value(
        self,
        requested_type: type[T] | tuple[type[T], ...],
        field: DataAlias[HOST_DATA_OUT] | tuple[DataAlias[HOST_DATA_OUT], ...],
        *,
        timeout: int | None = None,
    ) -> Iterator[tuple[T, HOST_DATA_OUT]]:
        """
        Takes field (for example HostWrapper.id) and yields message together with value of field
        """
        if isinstance(requested_type, tuple):
            assert isinstance(field, tuple)
            type_map = dict(zip(requested_type, field, strict=False))
        else:
            assert not isinstance(field, tuple)
            type_map = {requested_type: field}

        message: T
        for message in self._walk_messages(requested_type, timeout=timeout):
            raw = message._raw_message
            assert raw is not None
            value: HOST_DATA_OUT
            current_field = type_map[type(message)]

            if isinstance(message, HostMessageWrapper):
                host = message.host

                try:
                    value = current_field.__get__(host, requested_type)
                except AttributeError:
                    continue
            else:
                try:
                    value = current_field.__get__(message, requested_type)
                except AttributeError:
                    continue

            log.debug(
                "%s: (P:%s O:%s) %s %s",
                raw.topic(),
                raw.partition(),
                raw.offset(),
                current_field.name,
                value,
            )
            yield message, value

    def _walk_filtered_messages_with_value(
        self,
        requested_type: type[T] | tuple[type[T], ...],
        field: DataAlias[HOST_DATA_OUT] | tuple[DataAlias[HOST_DATA_OUT], ...],
        values: list[HOST_DATA_OUT] | set[HOST_DATA_OUT],
        *,
        timeout: int | None = None,
    ) -> Iterator[tuple[T, HOST_DATA_OUT]]:
        """
        Takes field (for example HostWrapper.id)
        and values to be filtered (instances of field type)
        and yields filtered messages together with filtered value
        """
        log.info("search messages having %s in %s", field, values)
        for message, value in self._walk_messages_with_value(
            requested_type, field, timeout=timeout
        ):
            if value in values:
                yield message, value

    def _wait_for_filtered_messages(
        self,
        requested_type: type[T] | tuple[type[T], ...],
        field: DataAlias[HOST_DATA_OUT] | tuple[DataAlias[HOST_DATA_OUT], ...],
        values: list[HOST_DATA_OUT],
        timeout: int | None = None,
    ) -> list[T]:
        """
        Takes field (for example HostWrapper.id)
        and values to be filtered (instances of field type)
        and waits for all values to be found in messages.
        Returns list of messages or raises error if not all values were found.
        """
        # We can't use sets because some fields are lists, which are unhashable
        yet_to_be_found = deepcopy(values)
        found: list[HOST_DATA_OUT] = []
        messages = []
        for message, value in self._walk_filtered_messages_with_value(
            requested_type, field, values, timeout=timeout
        ):
            yet_to_be_found.remove(value)
            found.append(value)
            messages.append(message)
            if not yet_to_be_found:
                return messages
        else:
            raise KafkaMessageNotFoundError(requested_type, field, yet_to_be_found, found)

    def walk_host_messages(self, *, timeout: int | None = None) -> Iterator[HostMessageWrapper]:
        return self._walk_messages(HostMessageWrapper, timeout=timeout)

    def walk_error_messages(
        self, *, timeout: int | None = None
    ) -> Iterator[ErrorNotificationWrapper]:
        return self._walk_messages(ErrorNotificationWrapper, timeout=timeout)

    def walk_host_messages_with_value(
        self,
        field: DataAlias[HOST_DATA_OUT],
        *,
        timeout: int | None = None,
    ) -> Iterator[tuple[HostMessageWrapper, HOST_DATA_OUT]]:
        """
        Takes field (for example HostWrapper.id) and yields message together with value of field
        """
        return self._walk_messages_with_value(HostMessageWrapper, field, timeout=timeout)

    def walk_filtered_host_messages_with_value(
        self,
        field: DataAlias[HOST_DATA_OUT],
        values: list[HOST_DATA_OUT] | set[HOST_DATA_OUT],
        *,
        timeout: int | None = None,
    ) -> Iterator[tuple[HostMessageWrapper, HOST_DATA_OUT]]:
        """
        Takes field (for example HostWrapper.id)
        and values to be filtered (instances of field type)
        and yields filtered messages together with filtered value
        """
        return self._walk_filtered_messages_with_value(
            HostMessageWrapper, field, values, timeout=timeout
        )

    def walk_filtered_host_messages(
        self,
        field: DataAlias[HOST_DATA_OUT],
        values: list[HOST_DATA_OUT],
        *,
        timeout: int | None = None,
    ) -> Iterator[HostMessageWrapper]:
        """
        Takes field (for example HostWrapper.id)
        and values to be filtered (instances of field type)
        and yields filtered messages
        """
        for message, _ in self.walk_filtered_host_messages_with_value(
            field, values, timeout=timeout
        ):
            yield message

    def wait_for_filtered_host_messages(
        self,
        field: DataAlias[HOST_DATA_OUT],
        values: list[HOST_DATA_OUT],
        timeout: int | None = None,
    ) -> list[HostMessageWrapper]:
        """
        Takes field (for example HostWrapper.id)
        and values to be filtered (instances of field type)
        and waits for all values to be found in host messages.
        Returns list of host messages or raises error if not all values were found.
        """
        return self._wait_for_filtered_messages(HostMessageWrapper, field, values, timeout)

    def wait_for_filtered_host_message(
        self,
        field: DataAlias[HOST_DATA_OUT],
        value: HOST_DATA_OUT,
        timeout: int | None = None,
    ) -> HostMessageWrapper:
        """
        Takes field (for example HostWrapper.id)
        and a value to be filtered (instance of field type)
        and waits for the value to be found in messages.
        Returns a host message or raises error if the value was not found.
        """
        return self.wait_for_filtered_host_messages(field, [value], timeout=timeout)[0]

    def verify_host_messages_not_produced(
        self,
        hosts: list[HostWrapper],
        field: DataAlias = HostWrapper.insights_id,
        timeout: int = 1,
    ) -> None:
        """Verify that the host kafka messages were not produced by HBI.

        :param list[HostWrapper] hosts: HBI shouldn't produce host messages for these hosts
        :param DataAlias field: This field (and its value) will be used to try to match the
            host event generated by HBI with the provided hosts.
            Default: insights_id
        :param int timeout: How long to wait for the host event to be generated.
            Default: 1
        :return None
        """
        assert field.name is not None
        values = [getattr(host, field.name) for host in hosts]
        with pytest.raises(KafkaMessageNotFoundError):
            self.wait_for_filtered_host_messages(field, values, timeout=timeout)

    def wait_for_filtered_error_message(
        self,
        field: DataAlias[HOST_DATA_OUT],
        value: HOST_DATA_OUT,
        timeout: int | None = None,
    ) -> ErrorNotificationWrapper:
        """
        Takes field (for example ErrorNotificationWrapper.display_name)
        and a value to be filtered (instance of field type)
        and waits for the value to be found in error notification messages.
        Returns an error notification message or raises error if the value was not found.
        """
        return self._wait_for_filtered_messages(
            ErrorNotificationWrapper, field, [value], timeout=timeout
        )[0]

    def wait_for_filtered_delete_notification_messages(
        self,
        field: DataAlias[HOST_DATA_OUT],
        values: list[HOST_DATA_OUT],
        timeout: int | None = None,
    ) -> list[DeleteNotificationWrapper]:
        """
        Takes field (for example DeleteNotificationWrapper.inventory_id)
        and values to be filtered (instances of field type)
        and waits for all values to be found in delete notification messages.
        Returns list of delete notification messages or raises error if not all values were found.
        """
        return self._wait_for_filtered_messages(
            DeleteNotificationWrapper, field, values, timeout=timeout
        )

    def wait_for_filtered_delete_notification_message(
        self,
        field: DataAlias[HOST_DATA_OUT],
        value: HOST_DATA_OUT,
        timeout: int | None = None,
    ) -> DeleteNotificationWrapper:
        """
        Takes field (for example DeleteNotificationWrapper.inventory_id)
        and a value to be filtered (instance of field type)
        and waits for the value to be found in delete notification messages.
        Returns a delete notification message or raises error if the value was not found.
        """
        return self.wait_for_filtered_delete_notification_messages(
            field, [value], timeout=timeout
        )[0]

    def wait_for_filtered_registered_notification_messages(
        self,
        field: DataAlias[HOST_DATA_OUT],
        values: list[HOST_DATA_OUT],
        timeout: int | None = None,
    ) -> list[RegisteredNotificationWrapper]:
        """
        Takes field (for example RegisteredNotificationWrapper.insights_id)
        and values to be filtered (instances of field type)
        and waits for all values to be found in registered notification messages.
        Returns list of registered notification messages or raises error if some values not found.
        """
        return self._wait_for_filtered_messages(
            RegisteredNotificationWrapper, field, values, timeout=timeout
        )

    def wait_for_filtered_registered_notification_message(
        self,
        field: DataAlias[HOST_DATA_OUT],
        value: HOST_DATA_OUT,
        timeout: int | None = None,
    ) -> RegisteredNotificationWrapper:
        """
        Takes field (for example RegisteredNotificationWrapper.insights_id)
        and a value to be filtered (instance of field type)
        and waits for the value to be found in registered notification messages.
        Returns a registered notification message or raises error if the value was not found.
        """
        return self.wait_for_filtered_registered_notification_messages(
            field, [value], timeout=timeout
        )[0]

    def wait_for_filtered_stale_notification_messages(
        self,
        field: DataAlias[HOST_DATA_OUT],
        values: list[HOST_DATA_OUT],
        timeout: int | None = None,
    ) -> list[StaleNotificationWrapper]:
        """
        Takes field (for example StaleNotificationWrapper.inventory_id)
        and values to be filtered (instances of field type)
        and waits for all values to be found in stale notification messages.
        Returns list of stale notification messages or raises error if not all values were found.
        """
        return self._wait_for_filtered_messages(
            StaleNotificationWrapper, field, values, timeout=timeout
        )

    def wait_for_filtered_stale_notification_message(
        self,
        field: DataAlias[HOST_DATA_OUT],
        value: HOST_DATA_OUT,
        timeout: int | None = None,
    ) -> StaleNotificationWrapper:
        """
        Takes field (for example StaleNotificationWrapper.inventory_id)
        and a value to be filtered (instance of field type)
        and waits for the value to be found in stale notification messages.
        Returns a stale notification message or raises error if the value was not found.
        """
        return self.wait_for_filtered_stale_notification_messages(field, [value], timeout=timeout)[
            0
        ]

    def make_host_events(self, *args: Any, **kwargs: Any) -> list[HostMessageWrapper]:
        warnings.warn(DEPRECATE_MAKE_HOST_EVENTS, stacklevel=2)
        return self.create_host_events(*args, **kwargs)

    def create_host_events(
        self,
        hosts_data: list[dict[str, Any]],
        *,
        metadata: dict | None = None,
        operation_args: dict[str, str] | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        field_to_match: DataAlias = HostWrapper.insights_id,
        timeout: int | None = None,
        quiet: bool = False,
        key: str | None = None,
    ) -> list[HostMessageWrapper]:
        """Send host kafka messages to platform.inventory.host-ingress topic and wait for the
            kafka host events generated by HBI.

        :param list[dict[str, Any]] hosts_data: (Required) List of host data to be used for hosts
            creation. The data should have a structure that is accepted by HBI. More info here:
            https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
        :param dict metadata: Used to pass data associated with the host from the ingress service
            to the backend applications (request_id, identity, S3 bucket URL, etc.).
            If not provided, correct identity and a random request_id will be generated.
        :param dict operation_args: Arguments that are passed to the operation. The only supported
            argument right now is 'defer_to_reporter'.
            No operation_args will be used by default.
        :param bool omit_metadata: If true, metadata will not be generated.
            Default: False
        :param bool omit_identity: If true, identity will not be generated.
            Default: False
        :param bool omit_request_id: If true, request_id will not be generated.
            Default: False
        :param DataAlias field_to_match: This field (and its value) will be used to match the
            host event generated by HBI with the provided host_data.
            Default: insights_id
        :param int timeout: How long to wait for the host event to be generated.
            Default: 10
        :param bool quiet: If true, the produced host messages will not be logged.
            Default: False
        :param str key: This will be used as a key for the produced kafka host messages.
            Default: None
        :return list[HostMessageWrapper]: Kafka host events generated by HBI.
        """
        log.info("producing host messages")
        self.produce_host_create_messages(
            hosts_data,
            metadata=metadata,
            operation_args=operation_args,
            omit_metadata=omit_metadata,
            omit_identity=omit_identity,
            omit_request_id=omit_request_id,
            flush=True,
            quiet=quiet,
            key=key,
        )
        if field_to_match.name is None:
            # This should never happen, I need it for mypy to be happy
            raise ValueError("This field doesn't have a name")
        if any(field_to_match.name not in host for host in hosts_data):
            raise ValueError(f"Some hosts don't have {field_to_match.name}, can't find events")

        values = [host[field_to_match.name] for host in hosts_data]
        return self.wait_for_filtered_host_messages(field_to_match, values, timeout=timeout)

    def create_hosts(
        self,
        hosts_data: list[dict[str, Any]],
        *,
        metadata: dict | None = None,
        operation_args: dict[str, str] | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        field_to_match: DataAlias = HostWrapper.insights_id,
        timeout: int | None = None,
        quiet: bool = False,
        key: str | None = None,
        wait_for_created: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> list[HostWrapper]:
        """Create new hosts by sending kafka messages to platform.inventory.host-ingress topic.

        :param list[dict[str, Any]] hosts_data: (Required) List of host data to be used for hosts
            creation. The data should have a structure that is accepted by HBI. More info here:
            https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
        :param dict metadata: Used to pass data associated with the host from the ingress service
            to the backend applications (request_id, identity, S3 bucket URL, etc.).
            If not provided, correct identity and a random request_id will be generated.
        :param dict operation_args: Arguments that are passed to the operation. The only supported
            argument right now is 'defer_to_reporter'.
            No operation_args will be used by default.
        :param bool omit_metadata: If true, metadata will not be generated.
            Default: False
        :param bool omit_identity: If true, identity will not be generated.
            Default: False
        :param bool omit_request_id: If true, request_id will not be generated.
            Default: False
        :param DataAlias field_to_match: This field (and its value) will be used to match the
            host event generated by HBI with the provided host_data.
            Default: insights_id
        :param int timeout: How long to wait for the host event to be generated.
            Default: 10
        :param bool quiet: If true, the produced host messages will not be logged.
            Default: False
        :param str key: This will be used as a key for the produced kafka host messages.
            Default: None
        :param bool wait_for_created: If True, this method will wait until the host is
            retrievable by API (it should be available instantly)
            Default: True
        :param bool register_for_cleanup: If True, the new host will be registered for a cleanup.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return list[HostWrapper]: Created hosts (extracted from the kafka events produced by HBI)
        """
        event_messages = self.create_host_events(
            hosts_data,
            metadata=metadata,
            operation_args=operation_args,
            omit_metadata=omit_metadata,
            omit_identity=omit_identity,
            omit_request_id=omit_request_id,
            field_to_match=field_to_match,
            timeout=timeout,
            quiet=quiet,
            key=key,
        )
        created_hosts = _sort_created_hosts(hosts_data, event_messages, field_to_match)

        if register_for_cleanup:
            self._host_inventory.cleanup.add_hosts(created_hosts, scope=cleanup_scope)

        if wait_for_created:
            self._host_inventory.apis.hosts.wait_for_created(created_hosts)

        return created_hosts

    def create_random_hosts(
        self,
        n: int,
        *,
        metadata: dict | None = None,
        operation_args: dict[str, str] | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        field_to_match: DataAlias = HostWrapper.insights_id,
        timeout: int | None = None,
        quiet: bool = False,
        key: str | None = None,
        wait_for_created: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> list[HostWrapper]:
        """Create new hosts by sending kafka messages to platform.inventory.host-ingress topic.
            These hosts will have random data.

        :param int n: (Required) Number of hosts to create.
        :param dict metadata: Used to pass data associated with the host from the ingress service
            to the backend applications (request_id, identity, S3 bucket URL, etc.).
            If not provided, correct identity and a random request_id will be generated.
        :param dict operation_args: Arguments that are passed to the operation. The only supported
            argument right now is 'defer_to_reporter'.
            No operation_args will be used by default.
        :param bool omit_metadata: If true, metadata will not be generated.
            Default: False
        :param bool omit_identity: If true, identity will not be generated.
            Default: False
        :param bool omit_request_id: If true, request_id will not be generated.
            Default: False
        :param DataAlias field_to_match: This field (and its value) will be used to match the
            host event generated by HBI with the provided host_data.
            Default: insights_id
        :param int timeout: How long to wait for the host event to be generated.
            Default: 10
        :param bool quiet: If true, the produced host messages will not be logged.
            Default: False
        :param str key: This will be used as a key for the produced kafka host messages.
            Default: None
        :param bool wait_for_created: If True, this method will wait until the host is
            retrievable by API (it should be available instantly)
            Default: True
        :param bool register_for_cleanup: If True, the new host will be registered for a cleanup.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return list[HostWrapper]: Created hosts (extracted from the kafka events produced by HBI)
        """
        hosts_data = self._host_inventory.datagen.create_n_hosts_data(n)

        return self.create_hosts(
            hosts_data,
            metadata=metadata,
            operation_args=operation_args,
            omit_metadata=omit_metadata,
            omit_identity=omit_identity,
            omit_request_id=omit_request_id,
            field_to_match=field_to_match,
            timeout=timeout,
            quiet=quiet,
            key=key,
            wait_for_created=wait_for_created,
            register_for_cleanup=register_for_cleanup,
            cleanup_scope=cleanup_scope,
        )

    def create_host(
        self,
        host_data: dict[str, Any] | None = None,
        *,
        metadata: dict | None = None,
        operation_args: dict | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        field_to_match: DataAlias = HostWrapper.insights_id,
        timeout: int | None = None,
        quiet: bool = False,
        key: str | None = None,
        wait_for_created: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> HostWrapper:
        """Create a new host by sending a kafka message to platform.inventory.host-ingress topic.

        :param dict[str, Any] host_data: (Required) host data to be used for host creation.
            The data should have a structure that is accepted by HBI. More info here:
            https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
        :param dict metadata: Used to pass data associated with the host from the ingress service
            to the backend applications (request_id, identity, S3 bucket URL, etc.).
            If not provided, correct identity and a random request_id will be generated.
        :param dict operation_args: Arguments that are passed to the operation. The only supported
            argument right now is 'defer_to_reporter'.
            No operation_args will be used by default.
        :param bool omit_metadata: If true, metadata will not be generated.
            Default: False
        :param bool omit_identity: If true, identity will not be generated.
            Default: False
        :param bool omit_request_id: If true, request_id will not be generated.
            Default: False
        :param DataAlias field_to_match: This field (and its value) will be used to match the
            host event generated by HBI with the provided host_data.
            Default: insights_id
        :param int timeout: How long to wait for the host event to be generated.
            Default: 10
        :param bool quiet: If true, the produced host messages will not be logged.
            Default: False
        :param str key: This will be used as a key for the produced kafka host messages.
            Default: None
        :param bool wait_for_created: If True, this method will wait until the host is
            retrievable by API (it should be available instantly)
            Default: True
        :param bool register_for_cleanup: If True, the new host will be registered for a cleanup.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return HostWrapper: Created host (extracted from the kafka event produced by HBI)
        """
        host_data = (
            host_data if host_data is not None else self._host_inventory.datagen.create_host_data()
        )
        return self.create_hosts(
            [host_data],
            metadata=metadata,
            operation_args=operation_args,
            omit_metadata=omit_metadata,
            omit_identity=omit_identity,
            omit_request_id=omit_request_id,
            field_to_match=field_to_match,
            timeout=timeout,
            quiet=quiet,
            key=key,
            wait_for_created=wait_for_created,
            register_for_cleanup=register_for_cleanup,
            cleanup_scope=cleanup_scope,
        )[0]

    def update_system_profile(
        self,
        host_data: dict[str, Any],
        *,
        metadata: dict | None = None,
        operation_args: dict | None = None,
        omit_metadata: bool = False,
        omit_identity: bool = False,
        omit_request_id: bool = False,
        field_to_match: DataAlias = HostWrapper.insights_id,
        timeout: int | None = None,
        quiet: bool = False,
        key: str | None = None,
    ) -> HostWrapper:
        """Update a hosts' system profile by sending a kafka message to
            platform.inventory.system-profile topic.

        :param dict[str, Any] host_data: (Required) host data to be used to update system profile.
            The data should have a structure that is accepted by HBI. More info here:
            https://inscope.corp.redhat.com/docs/default/Component/consoledot-pages/services/inventory/#expected-message-format
        :param dict metadata: Used to pass data associated with the host from the ingress service
            to the backend applications (request_id, identity, S3 bucket URL, etc.).
            If not provided, correct identity and a random request_id will be generated.
        :param dict operation_args: Arguments that are passed to the operation. The only supported
            argument right now is 'defer_to_reporter'.
            No operation_args will be used by default.
        :param bool omit_metadata: If true, metadata will not be generated.
            Default: False
        :param bool omit_identity: If true, identity will not be generated.
            Default: False
        :param bool omit_request_id: If true, request_id will not be generated.
            Default: False
        :param DataAlias field_to_match: This field (and its value) will be used to match the
            host event generated by HBI with the provided host_data.
            Default: insights_id
        :param int timeout: How long to wait for the host event to be generated.
            Default: 10
        :param bool quiet: If true, the produced host messages will not be logged.
            Default: False
        :param str key: This will be used as a key for the produced kafka host messages.
            Default: None
        :return HostWrapper: Updated host (extracted from the kafka event produced by HBI)
        """
        self.produce_sp_update_messages(
            [host_data],
            metadata=metadata,
            operation_args=operation_args,
            omit_metadata=omit_metadata,
            omit_identity=omit_identity,
            omit_request_id=omit_request_id,
            quiet=quiet,
            key=key,
        )
        if field_to_match.name is None:
            # This should never happen, I need it for mypy to be happy
            raise ValueError("This field doesn't have a name")
        if field_to_match.name not in host_data:
            raise ValueError(f"The host don't have {field_to_match.name}, can't find events")

        value = host_data[field_to_match.name]
        return self.wait_for_filtered_host_message(field_to_match, value, timeout=timeout).host
