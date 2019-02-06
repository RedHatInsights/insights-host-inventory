#!/usr/bin/env python

from contextlib import contextmanager
from subprocess import run
from os import getenv, putenv
from tempfile import TemporaryDirectory


PROMETHEUS_ENV_VAR = "prometheus_multiproc_dir"
LISTEN_PORT = getenv('LISTEN_PORT', 8080)


@contextmanager
def prometheus_temp_dir():
    """
    Creates a new temporary folder and sets it to the Prometheus’ environment variable.
    """
    with TemporaryDirectory() as temp_dir:
        orig = getenv(PROMETHEUS_ENV_VAR)
        putenv(PROMETHEUS_ENV_VAR, temp_dir)
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
    run(("gunicorn", "--log-config=logconfig.ini", "--log-level=debug", f"--bind={bind}", "run"))


if __name__ == "__main__":
    with prometheus_temp_dir():
        run_server()
