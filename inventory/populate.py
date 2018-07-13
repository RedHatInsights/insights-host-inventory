import random

import uuid
import os
import django
from django.db.transaction import atomic

# script to populate local database for development and test 
# how to run: python -m inventory.populate
#TODO: convert to management custom command

products = (["Red Hat Enterprise Linux"] * 75) + ["Openstack", "Red Hat Virtualization"]
versions = ["7.0", "7.1", "7.2", "7.3", "7.4", "7.5"]
accts = ["%07d" % n for n in range(1, 99)]


@atomic
def populate(count=100):
    from inventory.models import Asset, Tag

    def make_facts():
        return {
            "default": {
                "hostname": asset.display_name.replace("ent", "host"),
                "product": random.choice(products),
                "version": random.choice(versions),
            }
        }

    def make_tags(namespace):
        tag = Tag.objects.create(namespace=namespace, name="fun", value="times")
        tag.save()
        return tag

    def make_ids():
        return {"pmaas": str(uuid.uuid4()), "hccm": str(uuid.uuid4())}

    for x in range(count):
        acct = random.choice(accts)
        asset = Asset.objects.create(account=acct, display_name="ent_%d" % x)
        asset.facts = make_facts()
        asset.tags.add(make_tags(namespace=acct))
        asset.ids = make_ids()
        print(asset.ids["pmaas"])
        asset.save()


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "insights.settings")
    django.setup()
    populate()
