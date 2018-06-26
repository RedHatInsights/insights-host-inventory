import random

import uuid
import os
import django
from django.db.transaction import atomic

products = (["Red Hat Enterprise Linux"] * 75) + ["Openstack", "Red Hat Virtualization"]
versions = ["7.0", "7.1", "7.2", "7.3", "7.4", "7.5"]
accts = ["%07d" % n for n in range(1, 99)]


@atomic
def populate(count=100):
    from inventory.models import Entity

    def make_facts():
        return [
            dict(namespace="default", name="hostname", value=e.display_name.replace("ent", "host")),
            dict(namespace="default", name="product", value=random.choice(products)),
            dict(namespace="default", name="version", value=random.choice(versions))
        ]

    def make_ids():
        return {
            "pmaas": str(uuid.uuid4()),
            "hccm": str(uuid.uuid4())
        }

    for x in range(count):
        e = Entity.objects.create(
            account=random.choice(accts), display_name="ent_%d" % x
        )
        e.facts = make_facts()
        e.ids = make_ids()
        print(e.ids["pmaas"])
        e.save()


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insights.settings")
    django.setup()
    populate()
