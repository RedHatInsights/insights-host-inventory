from collections import namedtuple
from itertools import product
from tempfile import TemporaryFile

from yaml import safe_load

from utils.deploy import main as deploy

RESOURCE_TEMPLATES_INDEXES = {
    "insights-inventory-reaper": 0,
    "insights-host-delete": 1,
    "insights-inventory-mq-service": 2,
    "insights-inventory": 3,
}
TARGETS_INDEXES = {"prod": 0, "stage": 1}
DEPLOY_YML = """$schema: /some-schema

labels:
  some: labels

resourceTemplates:
- name: insights-inventory-reaper
  targets:
  - namespace:
      $ref: /host-inventory-prod.yml
    ref: master
    parameters:
      IMAGE_TAG: 626ae85
      REAPER_SUSPEND: 'true'
  - namespace:
      $ref: /stage-host-inventory-stage.yml
    ref: master
    parameters:
      IMAGE_TAG: 626ae85
      REAPER_SUSPEND: 'true'
- name: insights-host-delete
  parameters:
    REPLICAS: 1
  targets:
  - namespace:
      $ref: /host-inventory-prod.yml
    ref: master
    parameters:
      IMAGE_TAG: 587a4f3
  - namespace:
      $ref: /stage-host-inventory-stage.yml
    ref: master
    parameters:
      IMAGE_TAG: 587a4f3
- name: insights-inventory-mq-service
  parameters:
    REPLICAS: 1
  targets:
  - namespace:
      $ref: /host-inventory-prod.yml
    ref: master
    parameters:
      IMAGE_TAG: 626ae85
  - namespace:
      $ref: /stage-host-inventory-stage.yml
    ref: master
    parameters:
      IMAGE_TAG: 626ae85
- name: insights-inventory
  parameters:
    REPLICAS: 1
  targets:
  - namespace:
      $ref: /host-inventory-prod.yml
    ref: master
    parameters:
      IMAGE_TAG: 626ae85
      BULK_QUERY_SOURCE: xjoin
  - namespace:
      $ref: /stage-host-inventory-stage.yml
    ref: master
    parameters:
      IMAGE_TAG: 626ae85
      BULK_QUERY_SOURCE: xjoin
"""


Args = namedtuple("Args", ("promo_code",))


def _run_deploy(promo_code, inp_):
    args = Args(promo_code)

    with TemporaryFile("r+", encoding="utf-8") as inp, TemporaryFile("r+", encoding="utf-8") as outp:
        inp.write(inp_)
        inp.seek(0)

        deploy(args, inp, outp)

        outp.seek(0)
        return outp.read()


def _head(doc):
    lines = doc.split("\n")
    first_lines = lines[0:7]
    return "\n".join(first_lines)


def test_deploy_image_tag_is_replaced():
    promo_code = "abcd1234"

    expected = safe_load(DEPLOY_YML)
    resource_templates = (
        RESOURCE_TEMPLATES_INDEXES["insights-inventory-reaper"],
        RESOURCE_TEMPLATES_INDEXES["insights-inventory-mq-service"],
        RESOURCE_TEMPLATES_INDEXES["insights-inventory"],
    )
    for rt_i, t_i in product(resource_templates, TARGETS_INDEXES.values()):
        expected["resourceTemplates"][rt_i]["targets"][t_i]["parameters"]["IMAGE_TAG"] = promo_code

    result = _run_deploy(promo_code, DEPLOY_YML)
    assert safe_load(result) == expected


def test_deploy_formatting_is_not_broken():
    result = _run_deploy("abcd1234", DEPLOY_YML)
    assert _head(result) == _head(DEPLOY_YML)
