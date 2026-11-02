from datetime import timedelta
from unittest.mock import patch

from api.admin import ADMIN_HOSTS_ROUTE
from api.admin import ADMIN_HOSTS_URL_PATH
from app import create_app
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.environment import RuntimeEnvironment
from tests.helpers.test_utils import make_config
from tests.helpers.test_utils import set_environment


def test_configuration_with_env_vars():
    app_name = "brontocrane"
    path_prefix = "r/slaterock/platform"
    expected_base_url = f"/{path_prefix}/{app_name}"
    expected_api_path = f"{expected_base_url}/v1"
    expected_mgmt_url_path_prefix = "/mgmt_testing"
    culling_stale_warning_offset_days = 10
    culling_culled_offset_days = 20

    new_env = {
        "INVENTORY_DB_USER": "fredflintstone",
        "INVENTORY_DB_PASS": "bedrock1234",
        "INVENTORY_DB_HOST": "localhost",
        "INVENTORY_DB_PORT": "5432",
        "INVENTORY_DB_NAME": "SlateRockAndGravel",
        "INVENTORY_DB_POOL_TIMEOUT": "3",
        "INVENTORY_DB_POOL_SIZE": "8",
        "APP_NAME": app_name,
        "PATH_PREFIX": path_prefix,
        "INVENTORY_MANAGEMENT_URL_PATH_PREFIX": expected_mgmt_url_path_prefix,
        "CULLING_STALE_WARNING_OFFSET_DAYS": str(culling_stale_warning_offset_days),
        "CULLING_CULLED_OFFSET_DAYS": str(culling_culled_offset_days),
    }

    with set_environment(new_env):
        conf = make_config()

    assert conf.db_uri == "postgresql+psycopg2://fredflintstone:bedrock1234@localhost:5432/SlateRockAndGravel"
    assert conf.db_pool_timeout == 3
    assert conf.db_pool_size == 8
    assert conf.api_url_path_prefix == expected_api_path
    assert conf.mgmt_url_path_prefix == expected_mgmt_url_path_prefix
    assert conf.culling_stale_warning_offset_delta == timedelta(days=culling_stale_warning_offset_days)
    assert conf.culling_culled_offset_delta == timedelta(days=culling_culled_offset_days)


def test_config_default_settings():
    expected_api_path = "/api/inventory/v1"
    expected_mgmt_url_path_prefix = "/"

    # Make sure the runtime_environment variables are not set
    with set_environment(None):
        conf = make_config()

    assert conf.db_uri == "postgresql+psycopg2://insights:insights@localhost:5432/insights"
    assert conf.api_url_path_prefix == expected_api_path
    assert conf.mgmt_url_path_prefix == expected_mgmt_url_path_prefix
    assert conf.db_pool_timeout == 5
    assert conf.db_pool_size == 5
    assert conf.culling_stale_warning_offset_delta == timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
    assert conf.culling_culled_offset_delta == timedelta(seconds=CONVENTIONAL_TIME_TO_DELETE_SECONDS)


def test_config_development_settings():
    with set_environment({"INVENTORY_DB_POOL_TIMEOUT": "3"}):
        conf = make_config()

    assert conf.db_pool_timeout == 3


@patch(  # type: ignore [call-overload]
    "app.Config",
    **{
        "return_value.mgmt_url_path_prefix": "/",
        "return_value.api_url_path_prefix": ADMIN_HOSTS_URL_PATH.removesuffix(ADMIN_HOSTS_ROUTE),
        "return_value.unleash_token": "",
        "return_value.read_db_uri": None,
    },
)
def test_config_is_assigned_create_app_config(config):
    with patch("app.db.init_app"), patch("app.init_kessel"):
        application = create_app(RuntimeEnvironment.TEST)
    assert "INVENTORY_CONFIG" in application.app.config
    assert config.return_value == application.app.config["INVENTORY_CONFIG"]
