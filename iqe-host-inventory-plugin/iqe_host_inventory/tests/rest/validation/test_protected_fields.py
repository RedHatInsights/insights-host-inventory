# mypy: disallow-untyped-defs

"""
metadata:
  requirements: inv-mq-fields-protection
"""

import pytest

from iqe_host_inventory import ApplicationHostInventory

pytestmark = [pytest.mark.backend]


@pytest.mark.ephemeral
def test_create_host_with_invalid_create_date(host_inventory: ApplicationHostInventory) -> None:
    """
    Test Host Creation Ignores created Date.

    Ignore a 'created' date when it is included in the request body.

    metadata:
        assignee: fstavela
        importance: medium
        title: Inventory API: Ignore 'created' date when included in payload body
    """
    created = "this should be ignored"
    host_data = host_inventory.datagen.create_host_data(created=created)
    host = host_inventory.kafka.create_host(host_data)

    assert host.created != created


@pytest.mark.ephemeral
def test_create_host_with_invalid_updated_date(host_inventory: ApplicationHostInventory) -> None:
    """
    Test Host Creation Ignores updated Date.

    Ignore a 'updated' date when it is included in the request body.

    metadata:
        assignee: fstavela
        importance: medium
        title: Inventory: Ignore 'updated' date when included in payload body
    """
    updated = "this should be ignored"
    host_data = host_inventory.datagen.create_host_data(updated=updated)
    host = host_inventory.kafka.create_host(host_data)

    assert host.updated != updated


@pytest.mark.ephemeral
def test_create_host_with_invalid_last_check_in_date(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test Host Creation Ignores last_check_in Date.

    Ignore a 'last_check_in' date when it is included in the request body.

    metadata:
        assignee: zabikeno
        importance: medium
        title: Inventory: Ignore 'last_check_in' date when included in payload body
    """
    last_check_in = "this should be ignored"
    host_data = host_inventory.datagen.create_host_data(last_check_in=last_check_in)
    host = host_inventory.kafka.create_host(host_data)

    assert host.last_check_in != last_check_in


@pytest.mark.ephemeral
def test_create_host_with_id(host_inventory: ApplicationHostInventory) -> None:
    """
    Test Host Creation Ignores id.

    Ignore the 'id' field when it is included in the request body.

    metadata:
        assignee: fstavela
        importance: medium
        title: Inventory: Ignore 'id' field when included in payload body
    """
    host_id = "this should be ignored"
    host_data = host_inventory.datagen.create_host_data(id=host_id)
    host = host_inventory.kafka.create_host(host_data)

    assert host.id != host_id
