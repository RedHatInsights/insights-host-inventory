from __future__ import annotations

import datetime
import logging
from copy import deepcopy
from enum import Enum
from enum import auto
from operator import itemgetter
from typing import Any
from typing import NamedTuple

import pytest
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import DataAlias
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import KafkaMessageNotFoundError
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import generate_host_field_value
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_host_field_by_name
from iqe_host_inventory.utils.datagen_utils import get_id_facts
from iqe_host_inventory.utils.tag_utils import sort_tags

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]

ID_FACT_FIELDS = get_id_facts()

NO_UPDATE_FIELDS: dict[str, Field] = {
    **{x.name: x for x in ID_FACT_FIELDS},
    **{name: get_host_field_by_name(name) for name in ("org_id", "system_profile")},
}
# todo: ENUM


class FieldAction(Enum):
    scrub = auto()
    keep = auto()
    rand = auto()


class IdentifiersActions(NamedTuple):
    id: FieldAction = FieldAction.scrub
    id_facts: FieldAction = FieldAction.scrub

    def __repr__(self):
        return f"IdentifiersActions<id: {self.id.name}; id_facts: {self.id_facts.name}>"

    @property
    def field_to_match_host(self) -> DataAlias:
        if self.id is FieldAction.keep:
            return HostWrapper.id
        if self.id_facts is FieldAction.keep:
            return HostWrapper.subscription_manager_id
        return HostWrapper.system_profile


def _update_host_data(  # NOQA: C901
    host_data: dict[str, Any],
    original_host: HostWrapper,
    identifiers_action: IdentifiersActions,
    other_fields_action: FieldAction,
):
    # Non identifiers fields
    for key in list(host_data.keys()):
        # ESSNTL-5571: Remove this stale_timestamp check once it's removed from host_data
        if key == "stale_timestamp":
            continue

        if key not in NO_UPDATE_FIELDS:
            if other_fields_action is FieldAction.scrub:
                del host_data[key]
            elif other_fields_action is FieldAction.rand:
                host_data[key] = generate_host_field_value(get_host_field_by_name(key))

    # Identifiers fields

    # Host ID
    if identifiers_action.id is FieldAction.keep:
        host_data["id"] = original_host.id
    elif identifiers_action.id is FieldAction.rand:
        host_data["id"] = generate_uuid()

    # ID facts should not be in the message
    if identifiers_action.id_facts is FieldAction.scrub:
        for fact in ID_FACT_FIELDS:
            host_data.pop(fact.name, None)

    # Wrong ID facts should be in the message
    elif identifiers_action.id_facts is FieldAction.rand:
        for fact in ID_FACT_FIELDS:
            host_data[fact.name] = generate_host_field_value(fact)

    # provider_id and provider_type must either be both present or neither of them.
    # I delete them both from the payload because they would have a bad influence on the test
    host_data.pop("provider_type", None)
    host_data.pop("provider_id", None)

    return host_data


def _check_host_data(
    host_inventory: ApplicationHostInventory, host_data: dict[str, Any], host_id: str
):
    # Check that nothing has changed outside of system_profile
    response_host = host_inventory.apis.hosts.get_hosts_by_id_response(host_id).results[0]

    for key, value in host_data.items():
        # ESSNTL-5571:: Remove this stale_timestamp check once it's removed from host_data
        if key == "stale_timestamp":
            continue

        if key == "tags":
            response_value = host_inventory.apis.hosts.get_host_tags_response(host_id).results[
                host_id
            ]
            assert sort_tags(response_value) == sort_tags(value)
        elif key != "system_profile":
            response_value = getattr(response_host, key)
            if key == "facts":
                response_value = sorted(
                    (val.to_dict() for val in response_value),
                    key=itemgetter("namespace"),
                    reverse=True,
                )
            if isinstance(response_value, datetime.datetime):
                value = datetime.datetime.fromisoformat(value)
            assert response_value == value

    # Check system_profile
    response_system_profile = (
        host_inventory.apis.hosts
        .get_hosts_system_profile_response(host_id)
        .results[0]
        .system_profile
    ).to_dict()
    for key, value in list(response_system_profile.items()):
        if isinstance(value, datetime.datetime):
            response_system_profile[key] = value.isoformat()
        if value is None:
            del response_system_profile[key]
    assert host_data["system_profile"] == response_system_profile


def make_identifiers_correct_actions() -> list[IdentifiersActions]:
    keep = FieldAction.keep
    rand = FieldAction.rand
    IA = IdentifiersActions

    actions = [
        IA(id=keep),
        IA(id_facts=keep),
        IA(id=keep, id_facts=keep),
        IA(id=keep, id_facts=rand),
    ]
    assert len(actions) == len(set(actions))
    return actions


@pytest.mark.ephemeral
@pytest.mark.parametrize("other_fields_correct", FieldAction)
@pytest.mark.parametrize("identifiers_correct", make_identifiers_correct_actions(), ids=repr)
def test_system_profile_topic_update_correct(
    host_inventory: ApplicationHostInventory,
    identifiers_correct: IdentifiersActions,
    other_fields_correct: FieldAction,
):
    """Test System Profile Kafka Topic with correct identifiers
    metadata:
        requirements: inv-mq-system-profile-topic
        assignee: fstavela
        importance: high
        title: Inventory: System Profile Kafka Topic with correct identifiers
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["bios_vendor"] = "old_vendor"
    host_data["system_profile"].pop("bios_version", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    updated_host_data = _update_host_data(
        deepcopy(host_data), host, identifiers_correct, other_fields_correct
    )
    updated_host_data["system_profile"] = {"bios_vendor": "new_vendor", "bios_version": "1.23"}
    updated_host = host_inventory.kafka.update_system_profile(
        updated_host_data, field_to_match=identifiers_correct.field_to_match_host
    )
    assert host.id == updated_host.id
    host_inventory.apis.hosts.wait_for_system_profile_updated(
        host, bios_vendor="new_vendor", bios_version="1.23"
    )
    host_data["system_profile"]["bios_vendor"] = "new_vendor"
    host_data["system_profile"]["bios_version"] = "1.23"
    _check_host_data(host_inventory, host_data, host.id)


def make_miss_updates_actions() -> list[IdentifiersActions]:
    rand = FieldAction.rand
    keep = FieldAction.keep
    IA = IdentifiersActions

    actions = [
        IA(),
        IA(id=rand),
        IA(id_facts=rand),
        IA(id=rand, id_facts=keep),
        IA(id=rand, id_facts=rand),
    ]
    assert len(actions) == len(set(actions))
    return actions


@pytest.mark.ephemeral
@pytest.mark.parametrize("other_fields_correct", list(FieldAction))
@pytest.mark.parametrize("identifiers_correct", make_miss_updates_actions())
@iqe_blocker(iqe_blocker.jira("RHINENG-16546", category=iqe_blocker.PRODUCT_RFE))
def test_system_profile_topic_update_not_found(
    host_inventory: ApplicationHostInventory,
    identifiers_correct: IdentifiersActions,
    other_fields_correct: FieldAction,
):
    """Test System Profile Kafka Topic with wrong identifiers
    metadata:
        requirements: inv-mq-system-profile-topic, inv-mq-host-field-validation
        assignee: fstavela
        importance: medium
        negative: true
        title: Inventory: System Profile Kafka Topic with wrong identifiers
    """

    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["bios_vendor"] = "old_vendor"
    host_data["system_profile"].pop("bios_version", None)
    host = host_inventory.kafka.create_host(host_data=host_data)

    updated_host_data = _update_host_data(
        deepcopy(host_data), host, identifiers_correct, other_fields_correct
    )
    updated_host_data["system_profile"].update({
        "bios_vendor": "new_vendor",
        "bios_version": "1.23",
    })
    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.update_system_profile(
            updated_host_data,
            field_to_match=identifiers_correct.field_to_match_host,
            timeout=1,
        )

    _check_host_data(host_inventory, host_data, host.id)


@pytest.mark.ephemeral
def test_system_profile_topic_update_without_sp(host_inventory: ApplicationHostInventory):
    """Test System Profile Kafka Topic without providing system_profile
    metadata:
        requirements: inv-mq-system-profile-topic, inv-mq-host-field-validation
        assignee: fstavela
        importance: medium
        negative: true
        title: Inventory: System Profile Kafka Topic without providing system_profile
    """
    host_data = host_inventory.datagen.create_host_data()
    host = host_inventory.kafka.create_host(host_data=host_data)

    updated_host_data = deepcopy(host_data)
    del updated_host_data["system_profile"]
    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.update_system_profile(updated_host_data, timeout=1)

    _check_host_data(host_inventory, host_data, host.id)


@pytest.mark.ephemeral
def test_system_profile_topic_update_without_org_id(host_inventory: ApplicationHostInventory):
    """Test System Profile Kafka Topic without providing org_id
    metadata:
        requirements: inv-mq-system-profile-topic, inv-account-integrity
        assignee: fstavela
        importance: high
        negative: true
        title: Inventory: System Profile Kafka Topic without providing org_id
    """
    host_data = host_inventory.datagen.create_host_data()
    host = host_inventory.kafka.create_host(host_data)

    updated_host_data = deepcopy(host_data)
    del updated_host_data["org_id"]
    with pytest.raises(KafkaMessageNotFoundError):
        host_inventory.kafka.update_system_profile(updated_host_data, timeout=1)

    _check_host_data(host_inventory, host_data, host.id)


@pytest.mark.ephemeral
def test_system_profile_topic_update_without_platform_metadata(
    host_inventory: ApplicationHostInventory,
):
    """Test System Profile Kafka Topic without providing platform_metadata
    https://issues.redhat.com/browse/RHCLOUD-13868

    metadata:
        requirements: inv-mq-system-profile-topic
        assignee: fstavela
        importance: high
        title: Inventory: System Profile Kafka Topic without providing platform_metadata
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["bios_vendor"] = "old_vendor"
    host_data["system_profile"].pop("bios_version", None)
    host = host_inventory.kafka.create_host(host_data)

    updated_host_data = _update_host_data(
        deepcopy(host_data), host, IdentifiersActions(id=FieldAction.keep), FieldAction.keep
    )

    data_update = {"bios_vendor": "new_vendor", "bios_version": "1.23"}
    updated_host_data["system_profile"].update(data_update)
    updated_host = host_inventory.kafka.update_system_profile(
        updated_host_data, field_to_match=HostWrapper.id, omit_metadata=True
    )
    host_inventory.apis.hosts.wait_for_system_profile_updated(host, **data_update)  # type: ignore[arg-type]
    assert host.id == updated_host.id

    host_data["system_profile"].update(data_update)
    _check_host_data(host_inventory, host_data, host.id)
