from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics

from app.common import get_build_version
from app.config import Config
from app.environment import RuntimeEnvironment
from app.telemetry import init_otel


def when_ready(server):  # noqa: ARG001, needed by gunicorn
    config = Config(RuntimeEnvironment.SERVER)
    GunicornPrometheusMetrics.start_http_server_when_ready(config.metrics_port)


def post_fork(server, worker):  # noqa: ARG001, needed by gunicorn
    """Initialize OpenTelemetry per worker process.

    https://opentelemetry-python.readthedocs.io/en/stable/examples/fork-process-model/README.html
    """
    init_otel(service_name="host-inventory", service_version=get_build_version())


def child_exit(server, worker):  # noqa: ARG001, needed by gunicorn
    GunicornPrometheusMetrics.mark_process_dead_on_child_exit(worker.pid)
