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
    from inventory.models import Host

    def make_facts():
        return {
            "default": {
                "hostname": e.display_name.replace("ent", "host"),
                "product": random.choice(products),
                "version": random.choice(versions),
            }
        }

    def make_ids():
        return {"pmaas_id": str(uuid.uuid4()), "hccm_id": str(uuid.uuid4())}

    for x in range(count):
        acct = random.choice(accts)
        e = Host.objects.create(account=acct, display_name="ent_%d" % x)
        e.facts = make_facts()
        e.tags = [{"namespace": "testing", "key": "k", "value": "v"}]
        e.canonical_facts = make_ids()
        print(e.canonical_facts["pmaas_id"])
        e.save()


if __name__ == "__main__":
    import sys
    print(sys.path)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insights.settings")
    django.setup()
    populate()
