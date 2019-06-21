import os

from app.common import get_build_version
from app.logging import get_logger


class Config:
    SSL_VERIFY_FULL = "verify-full"

    def __init__(self):
        self.logger = get_logger(__name__)

        self._db_user = os.getenv("INVENTORY_DB_USER", "insights")
        self._db_password = os.getenv("INVENTORY_DB_PASS", "insights")
        self._db_host = os.getenv("INVENTORY_DB_HOST", "localhost")
        self._db_name = os.getenv("INVENTORY_DB_NAME", "insights")
        self._db_ssl_mode = os.getenv("INVENTORY_DB_SSL_MODE", "")
        self._db_ssl_cert = os.getenv("INVENTORY_DB_SSL_CERT", "")

        self.db_pool_timeout = int(os.getenv("INVENTORY_DB_POOL_TIMEOUT", "5"))
        self.db_pool_size = int(os.getenv("INVENTORY_DB_POOL_SIZE", "5"))

        self.db_uri = self._build_db_uri(self._db_ssl_mode)

        self.base_url_path = self._build_base_url_path()
        self.api_url_path_prefix = self._build_api_path()
        self.legacy_api_url_path_prefix = os.getenv("INVENTORY_LEGACY_API_URL", "")
        self.mgmt_url_path_prefix = os.getenv("INVENTORY_MANAGEMENT_URL_PATH_PREFIX", "/")

        self.api_urls = [self.api_url_path_prefix, self.legacy_api_url_path_prefix]

        self.system_profile_topic = os.environ.get("KAFKA_TOPIC", "platform.system-profile")
        self.consumer_group = os.environ.get("KAFKA_GROUP", "inventory")
        self.bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
        self.event_topic = os.environ.get("KAFKA_EVENT_TOPIC", "platform.inventory.events")
        self.kafka_enabled = all(map(os.environ.get, ["KAFKA_TOPIC", "KAFKA_GROUP", "KAFKA_BOOTSTRAP_SERVERS"]))

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

    def _build_db_uri(self, ssl_mode, hide_password=False):
        db_uri = f"postgresql://{self._db_user}:{self._db_password}@{self._db_host}/{self._db_name}"
        if ssl_mode == self.SSL_VERIFY_FULL:
            db_uri += f"?sslmode={self._db_ssl_mode}&sslrootcert={self._db_ssl_cert}"
        if hide_password:
            return db_uri.replace(self._db_password, "XXXX")
        return db_uri

    def log_configuration(self, config_name):
        if config_name != "testing":
            self.logger.info("Insights Host Inventory Configuration:")
            self.logger.info("Build Version: %s" % get_build_version())
            self.logger.info("API URL Path: %s" % self.api_url_path_prefix)
            self.logger.info("Management URL Path Prefix: %s" % self.mgmt_url_path_prefix)
            self.logger.info("DB Host: %s" % self._db_host)
            self.logger.info("DB Name: %s" % self._db_name)
            self.logger.info("DB Connection URI: %s" % self._build_db_uri(self._db_ssl_mode, hide_password=True))
            if self._db_ssl_mode == self.SSL_VERIFY_FULL:
                self.logger.info("Using SSL for DB connection:")
                self.logger.info("Postgresql SSL verification type: %s" % self._db_ssl_mode)
                self.logger.info("Path to certificate: %s" % self._db_ssl_cert)
