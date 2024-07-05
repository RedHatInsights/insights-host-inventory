#!/usr/bin/env python
from contextlib import contextmanager
from os import getenv
from os import putenv
from subprocess import run
from tempfile import TemporaryDirectory


PROMETHEUS_ENV_VAR = "prometheus_multiproc_dir"
LISTEN_PORT = getenv("LISTEN_PORT", 8080)


@contextmanager
def prometheus_temp_dir():
    """
    Creates a new temporary folder and sets it to the Prometheus' environment variable.
    """
    with TemporaryDirectory() as temp_dir:
        orig = getenv(PROMETHEUS_ENV_VAR)
        putenv(PROMETHEUS_ENV_VAR, temp_dir)
        putenv("BYPASS_RBAC", "true")
        putenv("BYPASS_TENANT_TRANSLATION", "true")
        try:
            yield
        finally:
            putenv(PROMETHEUS_ENV_VAR, orig)


def run_server():
    """
    Runs the Gunicorn server in a new subprocess. This way it gets the new environment
    variables.
    """
    bind = f"0.0.0.0:{LISTEN_PORT}"
    run(
        (
            "gunicorn", 
            "--log-level=debug",
            f"--bind={bind}",
            "--reload",
            "--worker-class=uvicorn.workers.UvicornWorker",
            "run:app",
        )
    )


if __name__ == "__main__":
    with prometheus_temp_dir():
        run_server()
