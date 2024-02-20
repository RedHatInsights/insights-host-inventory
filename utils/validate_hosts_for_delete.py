from marshmallow import ValidationError

from app import create_app
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.queue.events import build_event
from app.queue.events import EventType

logger = get_logger("utils")


def test_validations(host):
    try:
        build_event(EventType.delete, host)
    except ValidationError as error:
        return error.messages
    else:
        return {}


def main():
    application = create_app(RuntimeEnvironment.COMMAND)
    with application.app.app_context() as ctx:
        threadctx.request_id = None
        ctx.push()
    query = Host.query
    logger.info("Validating delete event for hosts.")
    logger.info("Total number of hosts: %i", query.count())

    number_of_errors = 0
    for host in query.yield_per(1000):
        host_validation_errors = test_validations(host)
        if host_validation_errors:
            number_of_errors += 1
            logger.info("Output validation error host ID %s, error %s", host.id, host_validation_errors)
    logger.info("Number of Host Validation Errors: %i", number_of_errors)


if __name__ == "__main__":
    main()
