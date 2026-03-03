from __future__ import annotations

import pprint
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol
from typing import TypeVar
from typing import cast
from typing import overload

if TYPE_CHECKING:
    from confluent_kafka import Message

from iqe_mq._transforms import MessageWrapper as MqMessageWrapper

from iqe_host_inventory.schemas import PER_REPORTER_STALENESS

HOST_DATA_OUT = TypeVar("HOST_DATA_OUT")
T = TypeVar("T")


class HasName(Protocol):
    "protocol as mypy won't accept DataAlias as instance attribute"

    name: str | None


@dataclass(order=False, eq=False)
class DataAlias[HOST_DATA_OUT]:
    name: str | None = None
    lookup_alias: HasName | str = "_data"

    def _get_data_dict(self, instance: object) -> dict[str, Any]:
        dict_name = getattr(self.lookup_alias, "name", self.lookup_alias)
        assert isinstance(dict_name, str)
        data_dict = getattr(instance, dict_name, None)
        if data_dict is None:
            raise AttributeError(self.name, dict_name)
        return data_dict

    @overload
    def __get__(self, instance: None, owner: object) -> DataAlias[HOST_DATA_OUT]: ...

    @overload
    def __get__(self, instance: object, owner: object) -> HOST_DATA_OUT: ...

    def __get__(
        self, instance: object | None, owner: object
    ) -> HOST_DATA_OUT | DataAlias[HOST_DATA_OUT]:
        if instance is None:
            return self
        assert self.name is not None
        try:
            data_dict = self._get_data_dict(instance)
            return data_dict[self.name]
        except KeyError:
            raise AttributeError(self.name) from None

    def __set__(self, instance: object, value: HOST_DATA_OUT):
        assert self.name is not None
        data_dict = self._get_data_dict(instance)
        data_dict[self.name] = value

    def __set_name__(self, owner: object, name: str):
        self.name = name


@dataclass(order=False, eq=False)
class TimestampDataAlias(DataAlias[datetime]):
    @overload
    def __get__(self, instance: None, owner: object) -> TimestampDataAlias: ...

    @overload
    def __get__(self, instance: object, owner: object) -> datetime: ...

    def __get__(self, instance: object | None, owner: object) -> datetime | TimestampDataAlias:
        if instance is None:
            return self
        data: str | datetime = super().__get__(instance, owner)
        return datetime.fromisoformat(data) if isinstance(data, str) else data

    def __set__(self, instance: object, value: datetime) -> None:
        super().__set__(instance, value.isoformat())  # type: ignore


class HostWrapper:
    _data: dict[str, Any]

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __repr__(self) -> str:
        small = {**self._data, "system_profile": ...}
        return f"HostWrapper({pprint.pformat(small, indent=2, compact=True)})"

    def data(self) -> dict[str, Any]:
        return self._data

    def __delattr__(self, name: str) -> None:
        if name in self._data:
            del self._data[name]

    id = DataAlias[str]()
    reporter = DataAlias[str]()
    insights_id = DataAlias[str]()
    subscription_manager_id = DataAlias[str]()
    satellite_id = DataAlias[str]()
    bios_uuid = DataAlias[str]()
    ip_addresses = DataAlias[list[str]]()
    fqdn = DataAlias[str]()
    mac_addresses = DataAlias[str]()
    provider_id = DataAlias[str]()
    provider_type = DataAlias[str]()
    facts = DataAlias[Any]()
    tags = DataAlias[Any]()
    account = DataAlias[str]()
    org_id = DataAlias[str]()
    display_name = DataAlias[str]()
    ansible_host = DataAlias[str]()
    stale_timestamp = TimestampDataAlias()
    stale_warning_timestamp = TimestampDataAlias()
    culled_timestamp = TimestampDataAlias()
    created = TimestampDataAlias()
    updated = TimestampDataAlias()
    per_reporter_staleness = DataAlias[PER_REPORTER_STALENESS]()
    system_profile = DataAlias[dict[str, Any]]()
    groups = DataAlias[list[dict[str, str]]]()
    last_check_in = TimestampDataAlias()
    openshift_cluster_id = DataAlias[str]()

    @property
    def host_type(self) -> str:
        """
        Derive host_type from host and system profile data.

        Mirrors HostTypeDeriver.derive_host_type() (app.models.mixins) so test
        assertions reflect production behavior.

        Priority order:
        1. openshift_cluster_id set on host → "cluster"
        2. Explicit host_type in system_profile ("edge" or "cluster")
        3. bootc_status booted.image_digest present → "bootc"
        4. Default → "conventional"

        Returns:
            str: The derived host type ('cluster', 'edge', 'bootc', or 'conventional')
        """
        # Same order as HostTypeDeriver: openshift_cluster_id first
        if self._data.get("openshift_cluster_id"):
            return "cluster"

        system_profile = self._data.get("system_profile", {})

        sp_host_type = system_profile.get("host_type")
        if sp_host_type in {"edge", "cluster"}:
            return sp_host_type

        bootc_status = system_profile.get("bootc_status") or {}
        if isinstance(bootc_status, dict):
            image_digest = bootc_status.get("booted", {}).get("image_digest")
            if image_digest:
                return "bootc"

        return "conventional"


@dataclass(eq=False, order=False)
class HostMessageWrapper:
    _data: dict[str, Any]
    _raw_message: Message | None = None

    @classmethod
    def from_message(cls, msg: Message | MqMessageWrapper):
        value = cast(dict[str, Any], msg.value())
        data = {
            "host": HostWrapper(value.get("host", value)),
            "key": msg.key(),
            "headers": dict(msg.headers()),
            "topic": msg.topic(),
            "value": value,
        }
        return cls(data, msg)

    def data(self) -> dict[str, Any]:
        return self._data

    host = DataAlias[HostWrapper]()

    key = DataAlias[str]()
    value = DataAlias[dict[str, Any]]()
    headers = DataAlias[dict[str, Any]]()

    type = DataAlias[str](lookup_alias=value)


@dataclass(eq=False, order=False)
class BaseNotificationWrapper:
    _data: dict[str, Any]
    _raw_message: Message | None = field(repr=False, default=None)

    @classmethod
    def from_message(cls, msg: Message):
        value = msg.value()
        data = {
            "key": msg.key(),
            "headers": dict(msg.headers()),
            "topic": msg.topic(),
            "value": value,
        }
        return cls(data, msg)

    @classmethod
    def from_json_event(cls, event: dict[str, Any]):
        return cls({"value": event})

    def data(self) -> dict[str, Any] | Any:
        return self._data

    key = DataAlias[str]()
    value = DataAlias[dict[str, Any]]()
    headers = DataAlias[dict[str, Any]]()

    # message root
    org_id = DataAlias[str](lookup_alias=value)
    application = DataAlias[str](lookup_alias=value)
    bundle = DataAlias[str](lookup_alias=value)
    event_type = DataAlias[str](lookup_alias=value)
    timestamp = TimestampDataAlias(lookup_alias=value)

    context = DataAlias[dict[str, Any]](lookup_alias=value)
    events = DataAlias[list[dict[str, Any]]](lookup_alias=value)

    # events[0]
    @property
    def _first_event(self) -> dict[str, Any]:
        return self.events[0]

    payload = DataAlias[dict[str, Any]](lookup_alias="_first_event")
    metadata = DataAlias[dict[str, Any]](lookup_alias="_first_event")


@dataclass(eq=False, order=False)
class ErrorNotificationWrapper(BaseNotificationWrapper):
    """
    Example error notification:

    {
      "org_id": "3340851",
      "application": "inventory",
      "bundle": "rhel",
      "context": {
        "event_name": "Host Validation Error",
        "display_name": "rhiqe.16ae33d8-e00e-4186-abf1-58911c55a13f",
      },
      "events":[
        {
          "metadata": {},
          "payload": {
            "request_id": "8036bf25-4a48-4da8-8a85-036b4348b624",
            "display_name": "rhiqe.16ae33d8-e00e-4186-abf1-58911c55a13f",
            "canonical_facts": {
              "insights_id": "89dce1ec-3f23-4195-9dc1-89f558d53361",
              "subscription_manager_id": "89dce1ec-3f23-4195-9dc1-89f558d53361",
              "satellite_id": "89dce1ec-3f23-4195-9dc1-89f558d53361",
              "bios_uuid": "89dce1ec-3f23-4195-9dc1-89f558d53361",
              "ip_addresses": [
                "192.168.115.41",
                "10.39.61.241"
              ],
              "fqdn": "rhiqe.laptop-37.robbins-ortiz.com",
              "mac_addresses": [
                "78:70:e8:58:07:4b",
                "da:fd:ec:ea:d2:5a"
              ],
              "provider_id": None,
              "provider_type": None
            },
            "error": {
              "code": "VE001",
              "message": "The org_id in the identity does not match the org_id in the host.",
              "stack_trace": None,
              "severity": "error"
            }
          }
        }
      ],
      "event_type": "validation-error",
      "timestamp": "2024-08-13T09:40:22.878589+00:00"
    }
    """

    # context
    event_name = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)

    # events[0].payload
    request_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    display_name = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    canonical_facts = DataAlias[dict[str, Any]](lookup_alias=BaseNotificationWrapper.payload)
    error = DataAlias[dict[str, Any]](lookup_alias=BaseNotificationWrapper.payload)

    # events[0].payload.canonical_facts
    insights_id = DataAlias[str](lookup_alias=canonical_facts)
    subscription_manager_id = DataAlias[str](lookup_alias=canonical_facts)
    satellite_id = DataAlias[str](lookup_alias=canonical_facts)
    bios_uuid = DataAlias[str](lookup_alias=canonical_facts)
    ip_addresses = DataAlias[list[str]](lookup_alias=canonical_facts)
    fqdn = DataAlias[str](lookup_alias=canonical_facts)
    mac_addresses = DataAlias[list[str]](lookup_alias=canonical_facts)
    provider_id = DataAlias[str](lookup_alias=canonical_facts)
    provider_type = DataAlias[str](lookup_alias=canonical_facts)

    # events[0].payload.error
    code = DataAlias[str](lookup_alias=error)
    message = DataAlias[str](lookup_alias=error)
    stack_trace = DataAlias[Any](lookup_alias=error)
    severity = DataAlias[str](lookup_alias=error)


@dataclass(eq=False, order=False)
class DeleteNotificationWrapper(BaseNotificationWrapper):
    """
    Example delete notification:

    {
      "org_id": "3340851",
      "application": "inventory",
      "bundle": "rhel",
      "context": {
        "inventory_id": "a241a329-fa97-4060-ab1a-3f62eb9d3fc9",
        "hostname": "rhiqe.desktop-81.caldwell-griffin.com",
        "display_name": "rhiqe.8163a002-3983-46c0-be31-8c0d2f26552e",
        "rhel_version": "7.10",
        "tags": {
          "feTCFjk": {
            "bNoMlRS": [
              "GPZUGAcs"
            ]
          },
          "qHlXSDHZ": {
            "VHmzYN": [
              "TcIlxVe"
            ]
          }
        }
      },
      "events": [
        {
          "metadata": {},
          "payload": {
            "groups": [
              {
                "id": "acaa1636-de85-4368-8702-e61e75889c58",
                "name": "rhiqe.025c666d-32f0-4d57-811e-19ec580b089a"
              }
            ],
            "insights_id": "3f8fb7dd-fcde-4dd7-8064-fff42b366fd6",
            "subscription_manager_id": "33fb53ea-c51a-41c4-9171-96fc7db8af0b",
            "satellite_id": "cd3ef398-d982-4997-9321-dbb9704bdc2f"
          }
        }
      ],
      "event_type": "system-deleted",
      "timestamp": "2024-08-13T09:56:17.841185+00:00"
    }
    """

    # context
    inventory_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    hostname = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    display_name = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    rhel_version = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    tags = DataAlias[dict[str, str]](lookup_alias=BaseNotificationWrapper.context)

    # events[0].payload
    insights_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    subscription_manager_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    satellite_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    groups = DataAlias[list[dict[str, str]]](lookup_alias=BaseNotificationWrapper.payload)


@dataclass(eq=False, order=False)
class RegisteredNotificationWrapper(BaseNotificationWrapper):
    """
    Example registered notification:

    {
      "org_id": "3340851",
      "application": "inventory",
      "bundle": "rhel",
      "context": {
        "inventory_id": "bb3999d4-7063-47fd-8524-f7714eec26a5",
        "hostname": "rhiqe.desktop-99.henry.org",
        "display_name": "rhiqe.29107221-93e5-4b11-b4ee-63123b667655",
        "rhel_version": "7.10",
        "tags": {
          "xgOOjr": {
            "TSeKCfRvy": [
              "WCHyO"
            ]
          },
          "zkjxxDSSJX": {
            "FvdUpWQ": [
              "zzimpsa"
            ]
          }
        },
        "host_url": "https://console.redhat.com/insights/inventory/4e52ff55-ec6d-4501-a6b6-306357f123fc"
      },
      "events": [
        {
          "metadata": {},
          "payload": {
            "groups": [],
            "insights_id": "13fadbe9-dcc5-4a2a-bcee-5f51b5816727",
            "subscription_manager_id": "1acb4a65-80de-4733-b123-e44c86b889bd",
            "satellite_id": "42545af3-95b6-4d1a-a4d9-60c065459dbf",
            "reporter": "yupana",
            "system_check_in": "2024-09-24T15:02:49.972527+00:00"
          }
        }
      ],
      "event_type": "new-system-registered",
      "timestamp": "2024-08-29T11:56:24.701112+00:00"
    }
    """

    # context
    inventory_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    hostname = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    display_name = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    rhel_version = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    tags = DataAlias[dict[str, str]](lookup_alias=BaseNotificationWrapper.context)
    host_url = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)

    # events[0].payload
    insights_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    subscription_manager_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    satellite_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    groups = DataAlias[list[dict[str, str]]](lookup_alias=BaseNotificationWrapper.payload)
    reporter = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    system_check_in = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)


@dataclass(eq=False, order=False)
class StaleNotificationWrapper(BaseNotificationWrapper):
    """
    Example stale notification:

    {
      "org_id": "3340851",
      "application": "inventory",
      "bundle": "rhel",
      "context": {
        "inventory_id": "bb3999d4-7063-47fd-8524-f7714eec26a5",
        "hostname": "rhiqe.desktop-99.henry.org",
        "display_name": "rhiqe.29107221-93e5-4b11-b4ee-63123b667655",
        "rhel_version": "7.10",
        "tags": {
          "xgOOjr": {
            "TSeKCfRvy": [
              "WCHyO"
            ]
          },
          "zkjxxDSSJX": {
            "FvdUpWQ": [
              "zzimpsa"
            ]
          }
        },
        "host_url": "https://console.redhat.com/insights/inventory/4e52ff55-ec6d-4501-a6b6-306357f123fc"
      },
      "events": [
        {
          "metadata": {},
          "payload": {
            "groups": [],
            "insights_id": "13fadbe9-dcc5-4a2a-bcee-5f51b5816727",
            "subscription_manager_id": "1acb4a65-80de-4733-b123-e44c86b889bd",
            "satellite_id": "42545af3-95b6-4d1a-a4d9-60c065459dbf",
          }
        }
      ],
      "event_type": "system-became-stale",
      "timestamp": "2024-08-29T11:56:24.701112+00:00"
    }
    """

    # context
    inventory_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    hostname = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    display_name = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    rhel_version = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)
    tags = DataAlias[dict[str, str]](lookup_alias=BaseNotificationWrapper.context)
    host_url = DataAlias[str](lookup_alias=BaseNotificationWrapper.context)

    # events[0].payload
    insights_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    subscription_manager_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    satellite_id = DataAlias[str](lookup_alias=BaseNotificationWrapper.payload)
    groups = DataAlias[list[dict[str, str]]](lookup_alias=BaseNotificationWrapper.payload)


@dataclass(eq=False, order=False)
class KesselOutboxWrapper:
    """Example kessel outbox event:

    {
      "schema":{
        "type":"struct",
        "fields":[
          {
            "type":"string",
            "optional":true,
            "field":"id"
          },
          {
            "type":"struct",
            "fields":[
              {
                "type":"struct",
                "fields":[
                  {
                    "type":"string",
                    "optional":true,
                    "field":"id"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"org_id"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"created_at"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"workspace_id"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"resource_type"
                  }
                ],
                "optional":true,
                "name":"payload.data.metadata",
                "field":"metadata"
              },
              {
                "type":"struct",
                "fields":[
                  {
                    "type":"string",
                    "optional":true,
                    "field":"api_href"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"console_href"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"reporter_type"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"reporter_version"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"local_resource_id"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"reporter_instance_id"
                  }
                ],
                "optional":true,
                "name":"payload.data.reporter_data",
                "field":"reporter_data"
              },
              {
                "type":"struct",
                "fields":[
                  {
                    "type":"string",
                    "optional":true,
                    "field":"insights_id"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"ansible_host"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"satellite_id"
                  },
                  {
                    "type":"string",
                    "optional":true,
                    "field":"subscription_manager_id"
                  }
                ],
                "optional":true,
                "name":"payload.data.resource_data",
                "field":"resource_data"
              }
            ],
            "optional":true,
            "name":"payload.data",
            "field":"data"
          },
          {
            "type":"string",
            "optional":true,
            "field":"time"
          },
          {
            "type":"string",
            "optional":true,
            "field":"type"
          },
          {
            "type":"string",
            "optional":true,
            "field":"source"
          },
          {
            "type":"string",
            "optional":true,
            "field":"subject"
          },
          {
            "type":"string",
            "optional":true,
            "field":"specversion"
          },
          {
            "type":"string",
            "optional":true,
            "field":"datacontenttype"
          }
        ],
        "optional":true,
        "name":"payload"
      },
      "payload":{
        "id":"df5753f5-ec9f-11f0-ae82-0a580a804a7b",
        "data":{
          "metadata":{
            "id":"019b9e0c-974a-70b2-81d0-05903177d9b7",
            "org_id":"",
            "created_at":"0001-01-01T00:00:00Z",
            "workspace_id":"019b9e0a-d518-7bb1-8b90-0f26dcf8037d",
            "resource_type":"host"
          },
          "reporter_data":{
            "api_href":"https://apihref.com/",
            "console_href":"https://www.console.com/",
            "reporter_type":"hbi",
            "reporter_version":"1.0",
            "local_resource_id":"29d99e76-0a07-4845-8e69-2c218cd4aee6",
            "reporter_instance_id":"redhat"
          },
          "resource_data":{
            "insights_id":"2755693d-c394-4998-9864-e6ed4793a289",
            "ansible_host":"rhiqe.desktop-25.johnson-dunn.org",
            "satellite_id":"f790ae9b-aef5-49de-802d-1d1126c5414c",
            "subscription_manager_id":"5a097ded-1c10-4245-8a87-b7448b1f5eff"
          }
        },
        "time":"0001-01-01T00:00:00Z",
        "type":"redhat.inventory.resources.host.created",
        "source":"",
        "subject":"/resources/host/019b9e0c-974a-70b2-81d0-05903177d9b7",
        "specversion":"1.0",
        "datacontenttype":"application/json"
      }
    }
    """

    _data: dict[str, Any]
    _raw_message: Message | None = field(repr=False, default=None)

    @classmethod
    def from_message(cls, msg: Message):
        value = msg.value()
        data = {
            "key": msg.key(),
            "headers": dict(msg.headers()),
            "topic": msg.topic(),
            "value": value,
        }
        return cls(data, msg)

    def data(self) -> dict[str, Any]:
        return self._data

    key = DataAlias[str]()
    value = DataAlias[dict[str, Any]]()
    headers = DataAlias[dict[str, Any]]()

    @property
    def payload_data(self) -> dict[str, Any]:
        return self.value.get("payload", {}).get("data", {})

    @property
    def metadata(self) -> dict[str, Any]:
        return self.payload_data.get("metadata", {})

    @property
    def workspace_id(self) -> str | None:
        return self.metadata.get("workspace_id")

    @property
    def reporter_data(self) -> dict[str, Any]:
        return self.payload_data.get("reporter_data", {})

    @property
    def host_id(self) -> str | None:
        return self.reporter_data.get("local_resource_id")

    @property
    def resource_data(self) -> dict[str, Any]:
        return self.payload_data.get("resource_data", {})

    @property
    def insights_id(self) -> str | None:
        return self.resource_data.get("insights_id")

    @property
    def subscription_manager_id(self) -> str | None:
        return self.resource_data.get("subscription_manager_id")

    @property
    def satellite_id(self) -> str | None:
        return self.resource_data.get("satellite_id")

    @property
    def ansible_host(self) -> str | None:
        return self.resource_data.get("ansible_host")


class KafkaMessageNotFoundError(LookupError):
    """raised when kafka messages were not found"""
