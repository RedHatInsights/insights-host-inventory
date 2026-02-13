#!/usr/bin/env python
import os

from app import create_app
from app.common import get_build_version
from app.environment import RuntimeEnvironment
from app.telemetry import init_otel

# Initialize OpenTelemetry before creating the app.
# When running under Gunicorn, this is handled by the post_fork hook instead.
init_otel(service_name="host-inventory", service_version=get_build_version())

app = create_app(RuntimeEnvironment.SERVER)


if __name__ == "__main__":
    listen_port = int(os.getenv("LISTEN_PORT", 8080))
    app.run(host="0.0.0.0", port=listen_port)
