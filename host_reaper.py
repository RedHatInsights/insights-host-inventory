from os import getenv

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import UNKNOWN_REQUEST_ID_VALUE
from app.config import Config
from app.culling import Conditions
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from lib.host_delete import delete_hosts
from lib.host_repository import stale_timestamp_filter
from tasks import flush
from tasks import init_tasks


__all__ = ("main",)
SELECT_CHUNK_SIZE = 1000


def _init_config(config_name):
    config = Config()
    config.log_configuration(config_name)
    return config


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def run(config, session):
    logger = get_logger("host_reaper")

    conditions = Conditions.from_config(config)
    query_filter = stale_timestamp_filter(*conditions.culled())
    query = session.query(Host).filter(query_filter).yield_per(SELECT_CHUNK_SIZE)

    events = delete_hosts(query)
    for host_id, deleted in events:
        if deleted:
            logger.info("Deleted host: %s", host_id)
        else:
            logger.info("Host %s already deleted. Delete event not emitted.", host_id)


def main(config_name):
    config = _init_config(config_name)
    init_tasks(config)

    Session = _init_db(config)
    session = Session()

    run(config, session)

    flush()

    session.commit()
    session.close()


if __name__ == "__main__":
    config_name = getenv("APP_SETTINGS", "development")
    configure_logging(config_name)
    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    main(config_name)
