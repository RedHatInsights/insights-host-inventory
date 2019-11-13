from app import create_app
from app import events
from app import UNKNOWN_REQUEST_ID_VALUE
from app.events import HostEvent
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host

logger = get_logger("utils")


def test_validations(host):
    schema = HostEvent()
    event = events.delete(host)
    deserialized = schema.loads(event)
    return deserialized.errors


def main():
    flask_app = create_app(config_name="validation_script")
    with flask_app.app_context() as ctx:
        threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
        ctx.push()
    query = Host.query
    logger.info(f"Validating delete event for hosts.")
    logger.info(f"Total number of hosts: %i", query.count())

    number_of_errors = 0
    for host in query.yield_per(1000):
        host_validation_errors = test_validations(host)
        if host_validation_errors:
            number_of_errors += 1
            logger.info("Output validation error host ID %s, error %s", host.id, host_validation_errors)
    logger.info("Number of Host Validation Errors: %i", number_of_errors)


if __name__ == "__main__":
    main()
