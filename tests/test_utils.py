from collections import namedtuple
from itertools import product
from tempfile import TemporaryFile
from unittest.mock import MagicMock
from unittest.mock import patch

from pytest import mark
from yaml import safe_load

from lib.feature_flags import FLAG_FALLBACK_VALUES
from lib.feature_flags import get_flag_value_and_fallback
from lib.feature_flags import UNLEASH
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
  - namespace:
      $ref: /stage-host-inventory-stage.yml
    ref: master
    parameters:
      IMAGE_TAG: 626ae85
"""


Args = namedtuple("Args", ("promo_code", "targets"))
TEST_FEATURE_FLAG = "foo.bar.test-feature"


def _run_deploy(promo_code, targets, inp_):
    args = Args(promo_code, targets)

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


@mark.parametrize(("args_targets"), ([], ["prod"], ["stage"], ["prod", "stage"]))
def test_deploy_image_tag_is_replaced(args_targets):
    promo_code = "abcd1234"

    expected = safe_load(DEPLOY_YML)
    resource_templates = (
        RESOURCE_TEMPLATES_INDEXES["insights-inventory-reaper"],
        RESOURCE_TEMPLATES_INDEXES["insights-inventory-mq-service"],
        RESOURCE_TEMPLATES_INDEXES["insights-inventory"],
    )
    targets = [v for k, v in TARGETS_INDEXES.items() if k in args_targets]
    for rt_i, t_i in product(resource_templates, targets):
        expected["resourceTemplates"][rt_i]["targets"][t_i]["parameters"]["IMAGE_TAG"] = promo_code

    result = _run_deploy(promo_code, args_targets, DEPLOY_YML)
    assert safe_load(result) == expected


def test_deploy_formatting_is_not_changed():
    result = _run_deploy("abcd1234", ["prod", "stage"], DEPLOY_YML)
    assert _head(result) == _head(DEPLOY_YML)


@patch.dict(FLAG_FALLBACK_VALUES, {TEST_FEATURE_FLAG: False})
def test_feature_flag_no_fallback(enable_unleash):
    unleash_mock = MagicMock()
    unleash_mock.is_enabled.return_value = True
    with patch.object(UNLEASH, "client", unleash_mock):
        flag_value, using_fallback = get_flag_value_and_fallback(TEST_FEATURE_FLAG)
        assert flag_value
        assert not using_fallback


@patch.dict(FLAG_FALLBACK_VALUES, {TEST_FEATURE_FLAG: False})
def test_feature_flag_error_fallback(enable_unleash):
    unleash_mock = MagicMock()
    unleash_mock.is_enabled.side_effect = ConnectionError("something went wrong :<")
    with patch.object(UNLEASH, "client", unleash_mock):
        flag_value, using_fallback = get_flag_value_and_fallback(TEST_FEATURE_FLAG)
        assert not flag_value
        assert using_fallback


@patch.dict(FLAG_FALLBACK_VALUES, {TEST_FEATURE_FLAG: False})
def test_feature_uninitialized_fallback(enable_unleash):
    with patch.object(UNLEASH, "client", None):
        flag_value, using_fallback = get_flag_value_and_fallback(TEST_FEATURE_FLAG)
        assert not flag_value
        assert using_fallback
