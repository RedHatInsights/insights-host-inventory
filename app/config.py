from __future__ import annotations

import json
import os
import tempfile
from datetime import timedelta

from app.common import get_build_version
from app.culling import days_to_seconds
from app.environment import RuntimeEnvironment
from app.logging import get_logger

PRODUCER_ACKS = {"0": 0, "1": 1, "all": "all"}

HOST_TYPES = ["edge", None]
ALL_STALENESS_STATES = ["fresh", "stale", "stale_warning"]


class Config:
    SSL_VERIFY_FULL = "verify-full"

    def clowder_config(self):
        import app_common_python

        cfg = app_common_python.LoadedConfig

        self.is_clowder = True
        self.metrics_port = cfg.metricsPort
        self.metrics_path = cfg.metricsPath
        self._db_user = cfg.database.username
        self._db_password = cfg.database.password
        self._db_host = cfg.database.hostname
        self._db_port = cfg.database.port
        self._db_name = cfg.database.name
        if cfg.database.rdsCa:
            self._db_ssl_cert = cfg.rds_ca()

        use_read_replica = os.getenv("INVENTORY_API_USE_READREPLICA", "false").lower() == "true"
        read_replica_file_list = [
            "/etc/db/readreplica/db_host",
            "/etc/db/readreplica/db_port",
            "/etc/db/readreplica/db_name",
            "/etc/db/readreplica/db_user",
            "/etc/db/readreplica/db_password",
        ]
        if use_read_replica and all(list(map(os.path.isfile, read_replica_file_list))):
            self.logger.info("Read replica files exist.")
            with open("/etc/db/readreplica/db_host") as file:
                self._db_host = file.read().rstrip()
            with open("/etc/db/readreplica/db_port") as file:
                self._db_port = file.read().rstrip()
            with open("/etc/db/readreplica/db_name") as file:
                self._db_name = file.read().rstrip()
            with open("/etc/db/readreplica/db_user") as file:
                self._db_user = file.read().rstrip()
            with open("/etc/db/readreplica/db_password") as file:
                self._db_password = file.read().rstrip()
        self._cache_host = None
        self._cache_port = None
        if cfg.inMemoryDb:
            self._cache_host = cfg.inMemoryDb.hostname
            self._cache_port = cfg.inMemoryDb.port

        self.rbac_endpoint = ""
        for endpoint in cfg.endpoints:
            if endpoint.app == "rbac":
                protocol = "https" if cfg.tlsCAPath else "http"
                port = endpoint.tlsPort if cfg.tlsCAPath else endpoint.port
                self.rbac_endpoint = f"{protocol}://{endpoint.hostname}:{port}"
                break

        self.export_service_endpoint = ""
        for endpoint in cfg.privateEndpoints:
            if endpoint.app == "export-service":
                protocol = "https" if cfg.tlsCAPath else "http"
                port = endpoint.tlsPort if cfg.tlsCAPath else endpoint.port
                self.export_service_endpoint = f"{protocol}://{endpoint.hostname}:{port}"
                break

        self.export_service_token = os.environ.get("EXPORT_SERVICE_TOKEN", "testing-a-psk")

        def topic(t):
            if t:
                t_topic = app_common_python.KafkaTopics.get(t)
                if t_topic:
                    return t_topic.name
            return None

        self.host_ingress_topic = topic(os.environ.get("KAFKA_HOST_INGRESS_TOPIC"))
        self.additional_validation_topic = topic(os.environ.get("KAFKA_ADDITIONAL_VALIDATION_TOPIC"))
        self.system_profile_topic = topic(os.environ.get("KAFKA_SYSTEM_PROFILE_TOPIC"))
        self.kafka_consumer_topic = topic(os.environ.get("KAFKA_CONSUMER_TOPIC"))
        self.notification_topic = topic(os.environ.get("KAFKA_NOTIFICATION_TOPIC"))
        self.event_topic = topic(os.environ.get("KAFKA_EVENT_TOPIC"))
        self.payload_tracker_kafka_topic = topic("platform.payload-status")
        self.export_service_topic = topic(os.environ.get("KAFKA_EXPORT_SERVICE_TOPIC", "platform.export.requests"))
        self.workspaces_topic = topic(os.environ.get("KAFKA_WORKSPACES_TOPIC"))

        self.bootstrap_servers = ",".join(app_common_python.KafkaServers)
        if custom_broker := os.getenv("CONSUMER_MQ_BROKER"):
            self.bootstrap_servers = custom_broker

        broker_cfg = cfg.kafka.brokers[0]

        # certificates are required in fedramp, but not in managed kafka
        try:
            self.kafka_ssl_cafile = self._kafka_ca(broker_cfg.cacert)
        except AttributeError:
            self.kafka_ssl_cafile = None
        try:
            self.kafka_sasl_username = broker_cfg.sasl.username
            self.kafka_sasl_password = broker_cfg.sasl.password
            self.kafka_sasl_mechanism = broker_cfg.sasl.saslMechanism
            self.kafka_security_protocol = broker_cfg.sasl.securityProtocol
        except AttributeError:
            self.kafka_sasl_username = ""
            self.kafka_sasl_password = ""
            self.kafka_sasl_mechanism = "PLAIN"
            self.kafka_security_protocol = "PLAINTEXT"

        # Feature flags
        unleash = cfg.featureFlags
        self.unleash_cache_directory = os.getenv("UNLEASH_CACHE_DIR", "/tmp/.unleashcache")
        if unleash:
            self.unleash_token = unleash.clientAccessToken
            self.unleash_url = f"{unleash.scheme.value}://{unleash.hostname}:{unleash.port}/api"
        else:
            self.unleash_url = os.getenv("UNLEASH_URL")
            self.unleash_token = os.getenv("UNLEASH_TOKEN")

    def non_clowder_config(self):
        self.is_clowder = False
        self.metrics_port = 9126
        self.metrics_path = "/metrics"
        self._db_user = os.getenv("INVENTORY_DB_USER", "insights")
        self._db_password = os.getenv("INVENTORY_DB_PASS", "insights")
        self._db_host = os.getenv("INVENTORY_DB_HOST", "localhost")
        self._db_port = os.getenv("INVENTORY_DB_PORT", 5432)
        self._db_name = os.getenv("INVENTORY_DB_NAME", "insights")
        self.rbac_endpoint = os.environ.get("RBAC_ENDPOINT", "http://localhost:8111")
        self.export_service_endpoint = os.environ.get("EXPORT_SERVICE_ENDPOINT", "http://localhost:10010")
        self.host_ingress_topic = os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress")
        self.additional_validation_topic = os.environ.get(
            "KAFKA_ADDITIONAL_VALIDATION_TOPIC", "platform.inventory.host-ingress-p1"
        )
        self.system_profile_topic = os.environ.get("KAFKA_SYSTEM_PROFILE_TOPIC", "platform.inventory.system-profile")
        self.kafka_consumer_topic = os.environ.get("KAFKA_CONSUMER_TOPIC", "platform.inventory.host-ingress")
        self.notification_topic = os.environ.get("KAFKA_NOTIFICATION_TOPIC", "platform.notifications.ingress")
        self.export_service_topic = os.environ.get("KAFKA_EXPORT_SERVICE_TOPIC", "platform.export.requests")
        self.workspaces_topic = os.environ.get("KAFKA_WORKSPACES_TOPIC", "outbox.event.workspace")
        self.bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
        self.event_topic = os.environ.get("KAFKA_EVENT_TOPIC", "platform.inventory.events")
        self.payload_tracker_kafka_topic = os.environ.get("PAYLOAD_TRACKER_KAFKA_TOPIC", "platform.payload-status")
        self._db_ssl_cert = os.getenv("INVENTORY_DB_SSL_CERT", "")
        self.kafka_ssl_cafile = os.environ.get("KAFKA_SSL_CAFILE")
        self.kafka_sasl_username = os.environ.get("KAFKA_SASL_USERNAME", "")
        self.kafka_sasl_password = os.environ.get("KAFKA_SASL_PASSWORD", "")
        self.kafka_security_protocol = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").upper()
        self.kafka_sasl_mechanism = os.environ.get("KAFKA_SASL_MECHANISM", "PLAIN").upper()

        self.unleash_url = os.environ.get("UNLEASH_URL", "http://unleash:4242/api")
        self.unleash_token = os.environ.get("UNLEASH_TOKEN", "")
        self._cache_host = os.environ.get("CACHE_HOST", "localhost")
        self._cache_port = os.environ.get("CACHE_PORT", "6379")
        self.export_service_token = os.environ.get("EXPORT_SERVICE_TOKEN", "testing-a-psk")

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
        self.db_statement_timeout = 0
        self.db_lock_timeout = 0
        # Allow configuring a statement timeout & lock_timeout on engine connection
        if runtime_environment == RuntimeEnvironment.SERVER:
            self.db_statement_timeout = int(os.getenv("INVENTORY_DB_STATEMENT_TIMEOUT", "30000"))
            self.db_lock_timeout = int(os.getenv("INVENTORY_DB_LOCK_TIMEOUT", "90000"))
        self.api_cache_timeout = int(os.getenv("INVENTORY_API_CACHE_TIMEOUT_SECONDS", "0"))
        self.api_cache_type = os.getenv("INVENTORY_API_CACHE_TYPE", "NullCache")
        self.cache_insights_client_system_timeout_sec = int(
            os.getenv("INVENTORY_CACHE_INSIGHTS_CLIENT_SYSTEM_TIMEOUT_SEC", "129600")
        )
        self.api_cache_max_thread_pool_workers = int(os.getenv("INVENTORY_CACHE_THREAD_POOL_MAX_WORKERS", "5"))

        self.db_uri = self._build_db_uri(self._db_ssl_mode)

        self.base_url_path = self._build_base_url_path()
        self.api_url_path_prefix = self._build_api_path()
        self.legacy_api_url_path_prefix = os.getenv("INVENTORY_LEGACY_API_URL", "/r/insights/platform/inventory/v1")
        self.mgmt_url_path_prefix = os.getenv("INVENTORY_MANAGEMENT_URL_PATH_PREFIX", "/")

        self.api_urls = [self.api_url_path_prefix, self.legacy_api_url_path_prefix]

        self.bypass_rbac = os.environ.get("BYPASS_RBAC", "false").lower() == "true"
        self.rbac_retries = os.environ.get("RBAC_RETRIES", 2)
        self.rbac_timeout = os.environ.get("RBAC_TIMEOUT", 10)

        self.bypass_unleash = os.environ.get("BYPASS_UNLEASH", "false").lower() == "true"
        self.unleash_refresh_interval = int(os.environ.get("UNLEASH_REFRESH_INTERVAL", "15"))

        self.bypass_tenant_translation = os.environ.get("BYPASS_TENANT_TRANSLATION", "false").lower() == "true"
        self.tenant_translator_url = os.environ.get("TENANT_TRANSLATOR_URL", "http://localhost:8892/internal/orgIds")

        self.host_ingress_consumer_group = os.environ.get("KAFKA_HOST_INGRESS_GROUP", "inventory-mq")
        self.inv_export_service_consumer_group = os.environ.get("KAFKA_EXPORT_SERVICE_GROUP", "inv-export-service")
        self.sp_validator_max_messages = int(os.environ.get("KAFKA_SP_VALIDATOR_MAX_MESSAGES", "10000"))

        self.prometheus_pushgateway = os.environ.get("PROMETHEUS_PUSHGATEWAY", "localhost:9091")
        self.kubernetes_namespace = os.environ.get("NAMESPACE")

        self.consoledot_hostname = os.getenv("CONSOLEDOT_HOSTNAME", "localhost")
        self.base_ui_url = f"https://{self.consoledot_hostname}/insights/inventory"

        self.kafka_ssl_configs = {
            "security.protocol": self.kafka_security_protocol,
            "ssl.ca.location": self.kafka_ssl_cafile,
            "sasl.mechanism": self.kafka_sasl_mechanism,
            "sasl.username": self.kafka_sasl_username,
            "sasl.password": self.kafka_sasl_password,
        }

        # https://github.com/edenhill/librdkafka/blob/master/CONFIGURATION.md
        self.kafka_consumer = {
            "request.timeout.ms": int(os.environ.get("KAFKA_CONSUMER_REQUEST_TIMEOUT_MS", "305000")),
            "max.in.flight.requests.per.connection": int(
                os.environ.get("KAFKA_CONSUMER_MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION", "5")
            ),
            "auto.offset.reset": os.environ.get("KAFKA_CONSUMER_AUTO_OFFSET_RESET", "latest"),
            "auto.commit.interval.ms": int(os.environ.get("KAFKA_CONSUMER_AUTO_COMMIT_INTERVAL_MS", "5000")),
            "max.poll.interval.ms": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_INTERVAL_MS", "300000")),
            "session.timeout.ms": int(os.environ.get("KAFKA_CONSUMER_SESSION_TIMEOUT_MS", "10000")),
            "heartbeat.interval.ms": int(os.environ.get("KAFKA_CONSUMER_HEARTBEAT_INTERVAL_MS", "3000")),
            "partition.assignment.strategy": "cooperative-sticky",
            **self.kafka_ssl_configs,
        }

        self.validator_kafka_consumer = {
            "group.id": "inventory-sp-validator",
            "request.timeout.ms": int(os.environ.get("KAFKA_CONSUMER_REQUEST_TIMEOUT_MS", "305000")),
            "max.in.flight.requests.per.connection": int(
                os.environ.get("KAFKA_CONSUMER_MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION", "5")
            ),
            "enable.auto.commit": False,
            "max.poll.interval.ms": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_INTERVAL_MS", "300000")),
            "session.timeout.ms": int(os.environ.get("KAFKA_CONSUMER_SESSION_TIMEOUT_MS", "10000")),
            "heartbeat.interval.ms": int(os.environ.get("KAFKA_CONSUMER_HEARTBEAT_INTERVAL_MS", "3000")),
            **self.kafka_ssl_configs,
        }

        self.events_kafka_consumer = {
            "group.id": "inventory-events-rebuild",
            "auto.offset.reset": "earliest",
            "queued.max.messages.kbytes": "65536",
            "request.timeout.ms": int(os.environ.get("KAFKA_CONSUMER_REQUEST_TIMEOUT_MS", "305000")),
            "max.in.flight.requests.per.connection": int(
                os.environ.get("KAFKA_CONSUMER_MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION", "5")
            ),
            "enable.auto.commit": False,
            "max.poll.interval.ms": int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_INTERVAL_MS", "300000")),
            "max.partition.fetch.bytes": int(os.environ.get("KAFKA_CONSUMER_MAX_PARTITION_FETCH_BYTES", "3145728")),
            "session.timeout.ms": int(os.environ.get("KAFKA_CONSUMER_SESSION_TIMEOUT_MS", "10000")),
            "heartbeat.interval.ms": int(os.environ.get("KAFKA_CONSUMER_HEARTBEAT_INTERVAL_MS", "3000")),
            **self.kafka_ssl_configs,
        }

        self.kafka_producer = {
            "acks": self._from_dict(PRODUCER_ACKS, "KAFKA_PRODUCER_ACKS", "1"),
            "retries": int(os.environ.get("KAFKA_PRODUCER_RETRIES", "0")),
            "batch.size": int(os.environ.get("KAFKA_PRODUCER_BATCH.SIZE", "16384")),
            "linger.ms": int(os.environ.get("KAFKA_PRODUCER_LINGER.MS", "0")),
            "retry.backoff.ms": int(os.environ.get("KAFKA_PRODUCER_RETRY.BACKOFF.MS", "100")),
            "max.in.flight.requests.per.connection": int(
                os.environ.get("KAFKA_PRODUCER_MAX.IN.FLIGHT.REQUESTS.PER.CONNECTION", "5")
            ),
            **self.kafka_ssl_configs,
        }

        self.max_poll_records = int(os.environ.get("KAFKA_CONSUMER_MAX_POLL_RECORDS", "10000"))

        self.payload_tracker_kafka_producer = {"bootstrap.servers": self.bootstrap_servers, **self.kafka_ssl_configs}
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

        self.conventional_time_to_stale_seconds = int(
            os.environ.get("CONVENTIONAL_TIME_TO_STALE_SECONDS", 104400)
        )  # 29 hours

        self.conventional_time_to_stale_warning_seconds = os.environ.get(
            "CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS", days_to_seconds(7)
        )

        self.conventional_time_to_delete_seconds = os.environ.get(
            "CONVENTIONAL_TIME_TO_DELETE_SECONDS", days_to_seconds(14)
        )

        self.immutable_time_to_stale_seconds = os.environ.get("IMMUTABLE_TIME_TO_STALE_SECONDS", days_to_seconds(2))

        self.immutable_time_to_stale_warning_seconds = os.environ.get(
            "IMMUTABLE_TIME_TO_STALE_WARNING_SECONDS", days_to_seconds(180)
        )

        self.immutable_time_to_delete_seconds = os.environ.get(
            "IMMUTABLE_TIME_TO_DELETE_SECONDS", days_to_seconds(730)
        )

        self.rbac_v2_force_org_admin = os.getenv("RBAC_V2_FORCE_ORG_ADMIN", "false").lower() == "true"
        self.use_sub_man_id_for_host_id = os.environ.get("USE_SUBMAN_ID", "false").lower() == "true"
        self.host_delete_chunk_size = int(os.getenv("HOST_DELETE_CHUNK_SIZE", "1000"))
        self.script_chunk_size = int(os.getenv("SCRIPT_CHUNK_SIZE", "500"))
        self.export_svc_batch_size = int(os.getenv("EXPORT_SVC_BATCH_SIZE", "500"))
        self.rebuild_events_time_limit = int(os.getenv("REBUILD_EVENTS_TIME_LIMIT", "3600"))  # 1 hour
        self.sp_authorized_users = os.getenv("SP_AUTHORIZED_USERS", "tuser@redhat.com").split()
        self.mq_db_batch_max_messages = int(os.getenv("MQ_DB_BATCH_MAX_MESSAGES", "1"))
        self.mq_db_batch_max_seconds = float(os.getenv("MQ_DB_BATCH_MAX_SECONDS", "0.5"))

        self.kessel_target_url = os.getenv("KESSEL_TARGET_URL", "localhost:9000")

        self.s3_access_key_id = os.getenv("S3_AWS_ACCESS_KEY_ID")
        self.s3_secret_access_key = os.getenv("S3_AWS_SECRET_ACCESS_KEY")
        self.s3_bucket = os.getenv("S3_AWS_BUCKET")

        self.sp_fields_to_log = os.getenv("SP_FIELDS_TO_LOG", "").split(",")

        try:
            self.api_bulk_tag_count_allowed = int(os.getenv("API_BULK_TAG_COUNT_ALLOWED", 10))
        except ValueError:
            self.api_bulk_tag_count_allowed = 10
        try:
            self.api_bulk_tag_host_batch_size = int(os.getenv("API_BULK_TAG_HOST_BATCH_SIZE", 100))
        except ValueError:
            self.api_bulk_tag_host_batch_size = 100

        # Load the RBAC PSKs into a dict, and then store the HBI one.
        # The structure looks like this:
        # {"inventory": {"secret": "psk-goes-here"}}
        try:
            _psk_dict = json.loads(os.environ.get("RBAC_PSKS", "{}"))
            self.rbac_psk = _psk_dict.get("inventory", {}).get("secret")
        except json.JSONDecodeError:
            self.logger.error("Failed to load RBAC PSKs from environment variable RBAC_PSKS")
            self.rbac_psk = None

        if self._runtime_environment == RuntimeEnvironment.PENDO_JOB:
            self.pendo_sync_active = os.environ.get("PENDO_SYNC_ACTIVE", "false").lower() == "true"
            self.pendo_endpoint = os.environ.get("PENDO_ENDPOINT", "https://app.pendo.io/api/v1")
            self.pendo_integration_key = os.environ.get("PENDO_INTEGRATION_KEY", "")
            self.pendo_retries = int(os.environ.get("PENDO_RETRIES", "3"))
            self.pendo_timeout = int(os.environ.get("PENDO_TIMEOUT", "240"))
            self.pendo_request_size = int(os.environ.get("PENDO_REQUEST_SIZE", "500"))

        if self._runtime_environment == RuntimeEnvironment.TEST:
            self.bypass_rbac = True
            self.bypass_tenant_translation = True
            self.bypass_unleash = True

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

            self.logger.info("Unleash (feature flags) Bypassed by config: %s", self.bypass_unleash)
            self.logger.info("Unleash (feature flags) Bypassed by missing token: %s", self.unleash_token is None)

            self.logger.info(
                "Bypassing tenant translation for hosts missing org_id: %s", self.bypass_tenant_translation
            )

        if self._runtime_environment == RuntimeEnvironment.SERVICE or self._runtime_environment.event_producer_enabled:
            self.logger.info("Kafka Bootstrap Servers: %s", self.bootstrap_servers)

            if self._runtime_environment == RuntimeEnvironment.SERVICE:
                self.logger.info("Kafka Host Ingress Topic: %s", self.host_ingress_topic)
                self.logger.info("Kafka System Profile Topic: %s", self.system_profile_topic)
                self.logger.info("Kafka Consumer Topic: %s", self.kafka_consumer_topic)
                self.logger.info("Kafka Consumer Group: %s", self.host_ingress_consumer_group)
                self.logger.info("Kafka Events Topic: %s", self.event_topic)
                self.logger.info("Kafka Notification Topic: %s", self.notification_topic)
                self.logger.info("Kafka Export Service Topic: %s", self.export_service_topic)
                self.logger.info("Export Service Endpoint: %s", self.export_service_endpoint)

            if self._runtime_environment.event_producer_enabled:
                self.logger.info("Kafka Event Topic: %s", self.event_topic)

            if self._runtime_environment.notification_producer_enabled:
                self.logger.info("Kafka Notification Topic: %s", self.notification_topic)

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
