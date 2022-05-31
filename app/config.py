import os
import tempfile
from datetime import timedelta

from app.common import get_build_version
from app.environment import RuntimeEnvironment
from app.logging import get_logger

PRODUCER_ACKS = {"0": 0, "1": 1, "all": "all"}


class Config:
    SSL_VERIFY_FULL = "verify-full"

    def clowder_config(self):
        import app_common_python

        cfg = app_common_python.LoadedConfig

        self.metrics_port = cfg.metricsPort
        self.metrics_path = cfg.metricsPath
        self._db_user = cfg.database.username
        self._db_password = cfg.database.password
        self._db_host = cfg.database.hostname
        self._db_port = cfg.database.port
        self._db_name = cfg.database.name
        if cfg.database.rdsCa:
            self._db_ssl_cert = cfg.rds_ca()

        self.rbac_endpoint = ""
        for endpoint in cfg.endpoints:
            if endpoint.app == "rbac":
                self.rbac_endpoint = f"http://{endpoint.hostname}:{endpoint.port}"
                break

        broker_cfg = cfg.kafka.brokers[0]
        self.bootstrap_servers = f"{broker_cfg.hostname}:{broker_cfg.port}"

        def topic(t):
            return app_common_python.KafkaTopics[t].name

        self.host_ingress_topic = topic(os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress"))
        self.additional_validation_topic = topic(
            os.environ.get("KAFKA_ADDITIONAL_VALIDATION_TOPIC", "platform.inventory.host-ingress-p1")
        )
        self.system_profile_topic = topic(
            os.environ.get("KAFKA_SYSTEM_PROFILE_TOPIC", "platform.inventory.system-profile")
        )
        self.kafka_consumer_topic = topic(os.environ.get("KAFKA_CONSUMER_TOPIC", "platform.inventory.host-ingress"))
        self.event_topic = topic("platform.inventory.events")
        self.payload_tracker_kafka_topic = topic("platform.payload-status")
        try:
            self.kafka_ssl_cafile = self._kafka_ca(broker_cfg.cacert)
            self.kafka_sasl_username = broker_cfg.sasl.username
            self.kafka_sasl_password = broker_cfg.sasl.password
        except AttributeError:
            self.kafka_ssl_cafile = None
            self.kafka_sasl_username = ""
            self.kafka_sasl_password = ""

    def non_clowder_config(self):
        self.metrics_port = 9126
        self.metrics_path = "/metrics"
        self._db_user = os.getenv("INVENTORY_DB_USER", "insights")
        self._db_password = os.getenv("INVENTORY_DB_PASS", "insights")
        self._db_host = os.getenv("INVENTORY_DB_HOST", "localhost")
        self._db_port = os.getenv("INVENTORY_DB_PORT", 5432)
        self._db_name = os.getenv("INVENTORY_DB_NAME", "insights")
        self.rbac_endpoint = os.environ.get("RBAC_ENDPOINT", "http://localhost:8111")
        self.host_ingress_topic = os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress")
        self.additional_validation_topic = os.environ.get(
            "KAFKA_ADDITIONAL_VALIDATION_TOPIC", "platform.inventory.host-ingress-p1"
        )
        self.system_profile_topic = os.environ.get("KAFKA_SYSTEM_PROFILE_TOPIC", "platform.inventory.system-profile")
        self.kafka_consumer_topic = os.environ.get("KAFKA_CONSUMER_TOPIC", "platform.inventory.host-ingress")
        self.bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
        self.event_topic = os.environ.get("KAFKA_EVENT_TOPIC", "platform.inventory.events")
        self.payload_tracker_kafka_topic = os.environ.get("PAYLOAD_TRACKER_KAFKA_TOPIC", "platform.payload-status")
        self._db_ssl_cert = os.getenv("INVENTORY_DB_SSL_CERT", "")
        self.kafka_ssl_cafile = os.environ.get("KAFKA_SSL_CAFILE")
        self.kafka_sasl_username = os.environ.get("KAFKA_SASL_USERNAME", "")
        self.kafka_sasl_password = os.environ.get("KAFKA_SASL_PASSWORD", "")

    def __init__(self, runtime_environment):
        self.logger = get_logger(__name__)
        self._runtime_environment = runtime_environment

        if os.getenv("CLOWDER_ENABLED", "").lower() == "true":
            self.clowder_config()
        else:
            self.non_clowder_config()

        self._db_ssl_mode = os.getenv("INVENTORY_DB_SSL_MODE", "")
        self.db_pool_timeout = int(os.getenv("INVENTORY_DB_POOL_TIMEOUT", "5"))
        self.db_pool_size = int(os.getenv("INVENTORY_DB_POOL_SIZE", "5"))

        self.db_uri = self._build_db_uri(self._db_ssl_mode)

        self.base_url_path = self._build_base_url_path()
        self.api_url_path_prefix = self._build_api_path()
        self.legacy_api_url_path_prefix = os.getenv("INVENTORY_LEGACY_API_URL", "")
        self.mgmt_url_path_prefix = os.getenv("INVENTORY_MANAGEMENT_URL_PATH_PREFIX", "/")

        self.api_urls = [self.api_url_path_prefix, self.legacy_api_url_path_prefix]

        self.bypass_rbac = os.environ.get("BYPASS_RBAC", "false").lower() == "true"
        self.rbac_retries = os.environ.get("RBAC_RETRIES", 2)
        self.rbac_timeout = os.environ.get("RBAC_TIMEOUT", 10)

        self.tenant_translator_url = os.environ.get("TENANT_TRANSLATOR_URL")
        self.bypass_tenant_translation = os.environ.get("BYPASS_TENANT_TRANSLATION", "false").lower() == "true"

        self.host_ingress_consumer_group = os.environ.get("KAFKA_HOST_INGRESS_GROUP", "inventory-mq")
        self.sp_validator_max_messages = int(os.environ.get("KAFKA_SP_VALIDATOR_MAX_MESSAGES", "10000"))

        self.prometheus_pushgateway = os.environ.get("PROMETHEUS_PUSHGATEWAY", "localhost:9091")
        self.kubernetes_namespace = os.environ.get("NAMESPACE")

        self.kafka_ssl_configs = {
            "security_protocol": os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").upper(),
            "ssl_cafile": self.kafka_ssl_cafile,
            "sasl_mechanism": os.environ.get("KAFKA_SASL_MECHANISM", "PLAIN").upper(),
            "sasl_plain_username": self.kafka_sasl_username,
            "sasl_plain_password": self.kafka_sasl_password,
        }

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
            **self.kafka_ssl_configs,
        }

        self.validator_kafka_consumer = {
            "group_id": "inventory-sp-validator",
            "request_timeout_ms": int(os.environ.get("KAFKA_CONSUMER_REQUEST_TIMEOUT_MS", "305000")),
            "max_in_flight_requests_per_connection": int(
                os.environ.get("KAFKA_CONSUMER_MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION", "5")
            ),
            "enable_auto_commit": False,
            "max_poll_records": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_RECORDS", "10000")),
            "max_poll_interval_ms": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_INTERVAL_MS", "300000")),
            "session_timeout_ms": int(os.environ.get("KAFKA_CONSUMER_SESSION_TIMEOUT_MS", "10000")),
            "heartbeat_interval_ms": int(os.environ.get("KAFKA_CONSUMER_HEARTBEAT_INTERVAL_MS", "3000")),
            **self.kafka_ssl_configs,
        }

        self.events_kafka_consumer = {
            "group_id": "inventory-events-rebuild",
            "request_timeout_ms": int(os.environ.get("KAFKA_CONSUMER_REQUEST_TIMEOUT_MS", "305000")),
            "max_in_flight_requests_per_connection": int(
                os.environ.get("KAFKA_CONSUMER_MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION", "5")
            ),
            "enable_auto_commit": False,
            "max_poll_records": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_RECORDS", "10000")),
            "max_poll_interval_ms": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_INTERVAL_MS", "300000")),
            "session_timeout_ms": int(os.environ.get("KAFKA_CONSUMER_SESSION_TIMEOUT_MS", "10000")),
            "heartbeat_interval_ms": int(os.environ.get("KAFKA_CONSUMER_HEARTBEAT_INTERVAL_MS", "3000")),
            **self.kafka_ssl_configs,
        }

        # https://kafka-python.readthedocs.io/en/1.4.7/apidoc/KafkaProducer.html#kafkaproducer
        self.kafka_producer = {
            "acks": self._from_dict(PRODUCER_ACKS, "KAFKA_PRODUCER_ACKS", "1"),
            "retries": int(os.environ.get("KAFKA_PRODUCER_RETRIES", "0")),
            "batch_size": int(os.environ.get("KAFKA_PRODUCER_BATCH_SIZE", "16384")),
            "linger_ms": int(os.environ.get("KAFKA_PRODUCER_LINGER_MS", "0")),
            "retry_backoff_ms": int(os.environ.get("KAFKA_PRODUCER_RETRY_BACKOFF_MS", "100")),
            "max_in_flight_requests_per_connection": int(
                os.environ.get("KAFKA_PRODUCER_MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION", "5")
            ),
            **self.kafka_ssl_configs,
        }

        self.payload_tracker_kafka_producer = {"bootstrap_servers": self.bootstrap_servers, **self.kafka_ssl_configs}

        self.payload_tracker_service_name = os.environ.get("PAYLOAD_TRACKER_SERVICE_NAME", "inventory")
        payload_tracker_enabled = os.environ.get("PAYLOAD_TRACKER_ENABLED", "true")
        self.payload_tracker_enabled = payload_tracker_enabled.lower() == "true"

        self.culling_stale_warning_offset_delta = timedelta(
            days=int(os.environ.get("CULLING_STALE_WARNING_OFFSET_DAYS", "7")),
            minutes=int(os.environ.get("CULLING_STALE_WARNING_OFFSET_MINUTES", "0")),
        )
        self.culling_culled_offset_delta = timedelta(
            days=int(os.environ.get("CULLING_CULLED_OFFSET_DAYS", "14")),
            minutes=int(os.environ.get("CULLING_CULLED_OFFSET_MINUTES", "0")),
        )

        self.xjoin_graphql_url = os.environ.get("XJOIN_GRAPHQL_URL", "http://localhost:4000/graphql")

        self.host_delete_chunk_size = int(os.getenv("HOST_DELETE_CHUNK_SIZE", "1000"))
        self.script_chunk_size = int(os.getenv("SCRIPT_CHUNK_SIZE", "1000"))
        self.sp_authorized_users = os.getenv("SP_AUTHORIZED_USERS", "tuser@redhat.com").split()

        if self._runtime_environment == RuntimeEnvironment.PENDO_JOB:
            self.pendo_sync_active = os.environ.get("PENDO_SYNC_ACTIVE", "false").lower() == "true"
            self.pendo_endpoint = os.environ.get("PENDO_ENDPOINT", "https://app.pendo.io/api/v1")
            self.pendo_integration_key = os.environ.get("PENDO_INTEGRATION_KEY", "")
            self.pendo_retries = int(os.environ.get("PENDO_RETRIES", "3"))
            self.pendo_timeout = int(os.environ.get("PENDO_TIMEOUT", "240"))
            self.pendo_request_size = int(os.environ.get("PENDO_REQUEST_SIZE", "500"))

        if self._runtime_environment == RuntimeEnvironment.TEST:
            self.bypass_rbac = "true"
            self.bypass_tenant_translation = "true"

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

        db_uri = f"postgresql://{db_user}:{db_password}@{self._db_host}:{self._db_port}/{self._db_name}"
        if ssl_mode == self.SSL_VERIFY_FULL:
            db_uri += f"?sslmode={self._db_ssl_mode}&sslrootcert={self._db_ssl_cert}"
        return db_uri

    def _from_dict(self, dict, name, default):
        value = dict.get(os.environ.get(name, default))

        if value is None:
            raise ValueError(f"{os.environ.get(name)} is not a valid value for {name}")
        return value

    def _kafka_ca(self, cacert_string):
        cacert_filename = None
        if cacert_string:
            with tempfile.NamedTemporaryFile(delete=False) as tf:
                cacert_filename = tf.name
                tf.write(cacert_string.encode("utf-8"))
        return cacert_filename

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

            self.logger.info("RBAC Bypassed: %s", self.bypass_rbac)
            self.logger.info("RBAC Endpoint: %s", self.rbac_endpoint)
            self.logger.info("RBAC Retry Times: %s", self.rbac_retries)
            self.logger.info("RBAC Timeout Seconds: %s", self.rbac_timeout)

            self.logger.info(
                "Populating missing org_ids on incoming hosts with dummy data: %s", self.bypass_tenant_translation
            )

        if self._runtime_environment == RuntimeEnvironment.SERVICE or self._runtime_environment.event_producer_enabled:
            self.logger.info("Kafka Bootstrap Servers: %s", self.bootstrap_servers)

            if self._runtime_environment == RuntimeEnvironment.SERVICE:
                self.logger.info("Kafka Host Ingress Topic: %s", self.host_ingress_topic)
                self.logger.info("Kafka System Profile Topic: %s", self.system_profile_topic)
                self.logger.info("Kafka Consumer Topic: %s", self.kafka_consumer_topic)
                self.logger.info("Kafka Consumer Group: %s", self.host_ingress_consumer_group)
                self.logger.info("Kafka Events Topic: %s", self.event_topic)

            if self._runtime_environment.event_producer_enabled:
                self.logger.info("Kafka Event Topic: %s", self.event_topic)

        if self._runtime_environment == RuntimeEnvironment.PENDO_JOB:
            self.logger.info("Pendo Sync Active: %s", self.pendo_sync_active)
            self.logger.info("Pendo Endpoint: %s", self.pendo_endpoint)

            self.logger.info("Pendo Retry Times: %s", self.pendo_retries)
            self.logger.info("Pendo Timeout Seconds: %s", self.pendo_timeout)

        if self._runtime_environment.payload_tracker_enabled:
            self.logger.info("Payload Tracker Kafka Topic: %s", self.payload_tracker_kafka_topic)
            self.logger.info("Payload Tracker Service Name: %s", self.payload_tracker_service_name)
            self.logger.info("Payload Tracker Enabled: %s", self.payload_tracker_enabled)

        if self._runtime_environment.metrics_pushgateway_enabled:
            self.logger.info("Metrics Pushgateway: %s", self.prometheus_pushgateway)
            self.logger.info("Kubernetes Namespace: %s", self.kubernetes_namespace)
