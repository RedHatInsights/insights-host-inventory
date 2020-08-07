from collections import namedtuple
from contextlib import contextmanager
from itertools import product
from tempfile import TemporaryFile

from pytest import fixture
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


@fixture(scope="function")
def temporary_file():
    @contextmanager
    def _fixture():
        with TemporaryFile("r+", encoding="utf-8") as file:
            yield file

    return _fixture


@fixture(scope="function")
def run_deploy(temporary_file):
    def _fixture(promo_code, inp_):
        args = Args(promo_code)

        with temporary_file() as inp, temporary_file() as outp:
            inp.write(inp_)
            inp.seek(0)

            deploy(args, inp, outp)

            outp.seek(0)
            return outp.read()

    return _fixture


@fixture(scope="session")
def head():
    def _fixture(doc):
        lines = doc.split("\n")
        first_lines = lines[0:7]
        return "\n".join(first_lines)

    return _fixture


def test_deploy_image_tag_is_replaced(run_deploy):
    promo_code = "abcd1234"

    expected = safe_load(DEPLOY_YML)
    resource_templates = (
        RESOURCE_TEMPLATES_INDEXES["insights-inventory-reaper"],
        RESOURCE_TEMPLATES_INDEXES["insights-inventory-mq-service"],
        RESOURCE_TEMPLATES_INDEXES["insights-inventory"],
    )
    for rt_i, t_i in product(resource_templates, TARGETS_INDEXES.values()):
        expected["resourceTemplates"][rt_i]["targets"][t_i]["parameters"]["IMAGE_TAG"] = promo_code

    result = run_deploy(promo_code, DEPLOY_YML)
    assert safe_load(result) == expected


def test_deploy_formatting_is_not_broken(run_deploy, head):
    result = run_deploy("abcd1234", DEPLOY_YML)
    assert head(result) == head(DEPLOY_YML)
