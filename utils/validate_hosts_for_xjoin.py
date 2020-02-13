from datetime import timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.host_query_xjoin import HostQueryResponseHostDataSchema
from app.config import Config
from app.logging import configure_logging
from app.logging import get_logger
from app.models import Host
from app.serialization import _CANONICAL_FACTS_FIELDS
from lib.db import session_guard

CONFIG_NAME = "validation_script"

logger = get_logger("utils")


def _init_db():
    config = Config(CONFIG_NAME)
    engine = create_engine(config.db_uri)
    Session = sessionmaker(engine)
    return Session()


def mock_xjoin_host_data(host):
    return {
        **{field: getattr(host, field) for field in ("account", "display_name", "facts", "ansible_host", "reporter")},
        **{
            field: getattr(host, field).astimezone(timezone.utc).isoformat() if getattr(host, field) else None
            for field in ("created_on", "modified_on", "stale_timestamp")
        },
        "id": str(host.id),
        "canonical_facts": {
            field: host.canonical_facts[field] for field in _CANONICAL_FACTS_FIELDS if field in host.canonical_facts
        },
        "facts": None,
    }


def validate_xjoin_host_data(host_data):
    schema = HostQueryResponseHostDataSchema()
    result = schema.load(host_data)
    return result.errors


def main():
    configure_logging(CONFIG_NAME)
    session = _init_db()
    with session_guard(session):
        query = session.query(Host)

        logger.info(f"Validating cross-join retrieval of hosts.")
        logger.info(f"Total number of hosts: %i", query.count())

        error_count = 0
        invalid_host_count = 0
        for host in query.yield_per(1000):
            xjoin_host_data = mock_xjoin_host_data(host)
            logger.debug("Cross-join host data: %s", xjoin_host_data)

            host_validation_errors = validate_xjoin_host_data(xjoin_host_data)
            if host_validation_errors:
                error_count += len(host_validation_errors)
                invalid_host_count += 1
                logger.info("Output validation error host ID %s, error %s", host.id, host_validation_errors)

        logger.info("Number of Host Validation Errors: %i", error_count)
        logger.info("Number of invalid Hosts: %i", invalid_host_count)


if __name__ == "__main__":
    main()
