import logging
import os

from app.common import get_build_version


class Config:
    def __init__(self, config_name):
        self.logger = logging.getLogger(__name__)
        self._config_name = config_name

        self._db_user = os.getenv("INVENTORY_DB_USER", "insights")
        self._db_password = os.getenv("INVENTORY_DB_PASS", "insights")
        self._db_host = os.getenv("INVENTORY_DB_HOST", "localhost")
        self._db_name = os.getenv("INVENTORY_DB_NAME", "insights")

        self.db_uri = f"postgresql://{self._db_user}:{self._db_password}@{self._db_host}/{self._db_name}"
        self.db_pool_timeout = int(os.getenv("INVENTORY_DB_POOL_TIMEOUT", "5"))
        self.db_pool_size = int(os.getenv("INVENTORY_DB_POOL_SIZE", "5"))

        self.base_url_path = self._build_base_url_path()
        self.api_url_path_prefix = self._build_api_path()
        self.legacy_api_url_path_prefix = os.getenv("INVENTORY_LEGACY_API_URL", "")
        self.mgmt_url_path_prefix = os.getenv("INVENTORY_MANAGEMENT_URL_PATH_PREFIX", "/")

        self.api_urls = [self.api_url_path_prefix, self.legacy_api_url_path_prefix]

        self._log_configuration()

    def _build_base_url_path(self):
        app_name = os.getenv("APP_NAME", "inventory")
        path_prefix = os.getenv("PATH_PREFIX", "api")
        base_url_path = f"/{path_prefix}/{app_name}"
        return base_url_path

    def _build_api_path(self):
        base_url_path = self._build_base_url_path()
        version = "v1"
        api_path = f"{base_url_path}/{version}"
        return api_path

    def _log_configuration(self):
        if self._config_name != "testing":
            self.logger.info("Insights Host Inventory Configuration:")
            self.logger.info("Build Version: %s" % get_build_version())
            self.logger.info("API URL Path: %s" % self.api_url_path_prefix)
            self.logger.info("Management URL Path Prefix: %s" % self.mgmt_url_path_prefix)
            self.logger.info("DB Host: %s" % self._db_host)
            self.logger.info("DB Name: %s" % self._db_name)
