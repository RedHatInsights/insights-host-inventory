# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import random

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_facts

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.ephemeral
def test_put_facts_replaces_all_facts(host_inventory: ApplicationHostInventory) -> None:
    """
    Test PUT replacement of all facts for a host.

    1. Create a host with facts
    2. Issue PUT with a new fact in the payload
    3. GET the host by id
    4. Confirm the old facts are present
    5. Confirm the new fact is present

    metadata:
        assignee: fstavela
        importance: medium
        title: Inventory: PUT replacement of all facts for a host
    """
    fancy_facts = generate_facts()
    host_data = host_inventory.datagen.create_host_data(facts=fancy_facts)
    host = host_inventory.kafka.create_host(host_data=host_data)

    fact_namespace = fancy_facts[0]["namespace"]
    new_facts = {"fact2": f"loves in the air - {random.randint(0, 999_999)}"}

    host_inventory.apis.hosts.replace_facts(
        host.id, namespace=fact_namespace, facts=new_facts, wait_for_updated=False
    )
    host_inventory.apis.hosts.wait_for_facts_replaced(host, fact_namespace, new_facts)
