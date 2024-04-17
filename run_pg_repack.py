#!/usr/bin/python
from os import environ
from subprocess import PIPE
from subprocess import Popen
from subprocess import STDOUT
from sys import exit

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx

__all__ = "main"

LOGGER_NAME = "inventory_pg_repack"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def _init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def log_subprocess_output(pipe):
    for line in iter(pipe.readline, b""):
        logger.info("pg_repack: %r", line)


def main(logger):
    cfg = _init_config()
    environ["PGPASSWORD"] = str(cfg._db_password)
    process = Popen(
        [
            "pg_repack",
            "-h",
            str(cfg._db_host),
            "-p",
            str(cfg._db_port),
            "-U",
            str(cfg._db_user),
            "-k",
            str(cfg._db_name),
            "-t",
            "hosts",
            "-t",
            "groups",
            "-t",
            "hosts_groups",
        ],
        stdout=PIPE,
        stderr=STDOUT,
    )

    with process.stdout:
        log_subprocess_output(process.stdout)

    returncode = process.wait()
    exit(returncode)


if __name__ == "__main__":
    configure_logging()
    logger = get_logger(LOGGER_NAME)
    threadctx.request_id = None
    main(logger)
