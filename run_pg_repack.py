import subprocess
from os import environ
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


def main(logger):
    cfg = _init_config()
    environ["PGPASSWORD"] = str(cfg._db_password)
    result = subprocess.run(
        [
            "pg_repack",
            "-a",
            "-h",
            str(cfg._db_host),
            "-p",
            str(cfg._db_port),
            "-U",
            str(cfg._db_user),
            "-k",
            str(cfg._db_name),
        ],
        capture_output=True,
    )
    logger.info(result.stdout)
    if result.returncode != 0 or result.stderr:
        logger.error(f"Call to pg_repack failed with error: {result.sterr}")
        exit(1)


if __name__ == "__main__":
    configure_logging()
    logger = get_logger(LOGGER_NAME)
    threadctx.request_id = None
    main(logger)
