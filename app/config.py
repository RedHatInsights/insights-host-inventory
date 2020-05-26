import os
from enum import Enum

from app.common import get_build_version
from app.environment import RuntimeEnvironment
from app.logging import get_logger

BulkQuerySource = Enum("BulkQuerySource", ("db", "xjoin"))


class Config:
    SSL_VERIFY_FULL = "verify-full"

    def __init__(self, runtime_environment):
        self.logger = get_logger(__name__)
        self._runtime_environment = runtime_environment

        self._db_user = os.getenv("INVENTORY_DB_USER", "insights")
        self._db_password = os.getenv("INVENTORY_DB_PASS", "insights")
        self._db_host = os.getenv("INVENTORY_DB_HOST", "localhost")
        default_db_name = "insights_test" if runtime_environment == RuntimeEnvironment.TEST else "insights"
        self._db_name = os.getenv("INVENTORY_DB_NAME", default_db_name)
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

        self.host_ingress_topic = os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress")
        self.host_ingress_consumer_group = os.environ.get("KAFKA_HOST_INGRESS_GROUP", "inventory-mq")
        self.host_egress_topic = os.environ.get("KAFKA_HOST_EGRESS_TOPIC", "platform.inventory.host-egress")
        self.system_profile_topic = os.environ.get("KAFKA_TOPIC", "platform.system-profile")
        self.bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
        self.event_topic = os.environ.get("KAFKA_EVENT_TOPIC", "platform.inventory.events")

        self.prometheus_pushgateway = os.environ.get("PROMETHEUS_PUSHGATEWAY", "localhost:9091")
        self.kubernetes_namespace = os.environ.get("NAMESPACE")

        # https://kafka-python.readthedocs.io/en/master/apidoc/KafkaConsumer.html#kafka.KafkaConsumer
        self.kafka_consumer = {
            "request_timeout_ms": int(os.environ.get("KAFKA_CONSUMER_REQUEST_TIMEOUT_MS", "305000")),
            "max_in_flight_requests_per_connection": int(
                os.environ.get("KAFKA_CONSUMER_MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION", "5")
            ),
            "auto_offset_reset": os.environ.get("KAFKA_CONSUMER_AUTO_OFFSET_RESET", "latest"),
            "auto_commit_interval_ms": int(os.environ.get("KAFKA_CONSUMER_AUTO_COMMIT_INTERVAL_MS", "5000")),
            "max_poll_records": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_RECORDS", "10")),
            "max_poll_interval_ms": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_INTERVAL_MS", "300000")),
            "session_timeout_ms": int(os.environ.get("KAFKA_CONSUMER_SESSION_TIMEOUT_MS", "10000")),
            "heartbeat_interval_ms": int(os.environ.get("KAFKA_CONSUMER_HEARTBEAT_INTERVAL_MS", "3000")),
        }

        self.payload_tracker_kafka_topic = os.environ.get("PAYLOAD_TRACKER_KAFKA_TOPIC", "platform.payload-status")
        self.payload_tracker_service_name = os.environ.get("PAYLOAD_TRACKER_SERVICE_NAME", "inventory")
        payload_tracker_enabled = os.environ.get("PAYLOAD_TRACKER_ENABLED", "true")
        self.payload_tracker_enabled = payload_tracker_enabled.lower() == "true"

        self.culling_stale_warning_offset_days = int(os.environ.get("CULLING_STALE_WARNING_OFFSET_DAYS", "7"))
        self.culling_culled_offset_days = int(os.environ.get("CULLING_CULLED_OFFSET_DAYS", "14"))

        self.xjoin_graphql_url = os.environ.get("XJOIN_GRAPHQL_URL", "http://localhost:4000/graphql")
        self.bulk_query_source = getattr(BulkQuerySource, os.environ.get("BULK_QUERY_SOURCE", "db"))
        self.bulk_query_source_beta = getattr(BulkQuerySource, os.environ.get("BULK_QUERY_SOURCE_BETA", "db"))

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
        db_user = self._db_user
        db_password = self._db_password

        if hide_password:
            db_user = "xxxx"
            db_password = "XXXX"

        db_uri = f"postgresql://{db_user}:{db_password}@{self._db_host}/{self._db_name}"
        if ssl_mode == self.SSL_VERIFY_FULL:
            db_uri += f"?sslmode={self._db_ssl_mode}&sslrootcert={self._db_ssl_cert}"
        return db_uri

    def log_configuration(self):
        if not self._runtime_environment.logging_enabled:
            return

        self.logger.info("Insights Host Inventory Configuration:")
        self.logger.info("Build Version: %s", get_build_version())
        self.logger.info("DB Host: %s", self._db_host)
        self.logger.info("DB Name: %s", self._db_name)
        self.logger.info("DB Connection URI: %s", self._build_db_uri(self._db_ssl_mode, hide_password=True))

        if self._db_ssl_mode == self.SSL_VERIFY_FULL:
            self.logger.info("Using SSL for DB connection:")
            self.logger.info("Postgresql SSL verification type: %s", self._db_ssl_mode)
            self.logger.info("Path to certificate: %s", self._db_ssl_cert)

        if self._runtime_environment == RuntimeEnvironment.SERVER:
            self.logger.info("API URL Path: %s", self.api_url_path_prefix)
            self.logger.info("Management URL Path Prefix: %s", self.mgmt_url_path_prefix)

        if self._runtime_environment == RuntimeEnvironment.SERVICE or self._runtime_environment.event_producer_enabled:
            self.logger.info("Kafka Bootstrap Servers: %s" % self.bootstrap_servers)

            if self._runtime_environment == RuntimeEnvironment.SERVICE:
                self.logger.info("Kafka Host Ingress Topic: %s" % self.host_ingress_topic)
                self.logger.info("Kafka Host Ingress Group: %s" % self.host_ingress_consumer_group)
                self.logger.info("Kafka Host Egress Topic: %s" % self.host_egress_topic)

            if self._runtime_environment.event_producer_enabled:
                self.logger.info("Kafka Event Topic: %s" % self.event_topic)

        if self._runtime_environment.payload_tracker_enabled:
            self.logger.info("Payload Tracker Kafka Topic: %s", self.payload_tracker_kafka_topic)
            self.logger.info("Payload Tracker Service Name: %s", self.payload_tracker_service_name)
            self.logger.info("Payload Tracker Enabled: %s", self.payload_tracker_enabled)

        if self._runtime_environment.metrics_pushgateway_enabled:
            self.logger.info("Metrics Pushgateway: %s", self.prometheus_pushgateway)
            self.logger.info("Kubernetes Namespace: %s", self.kubernetes_namespace)
