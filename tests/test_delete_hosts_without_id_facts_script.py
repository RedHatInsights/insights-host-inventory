from collections.abc import Callable

from connexion import FlaskApp
from pytest_mock import MockerFixture
from sqlalchemy.orm import Query

from app.models import Host
from app.models import db
from delete_hosts_without_id_facts import run
from jobs.common import init_config
from lib.handlers import ShutdownHandler
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.test_utils import generate_uuid


def test_delete_hosts_without_id_facts_happy_path(
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    db_get_hosts: Callable[[list[str]], Query],
    mocker: MockerFixture,
    event_producer_mock: MockEventProducer,
):
    host_with_provider_id = db_create_host(
        extra_data={"canonical_facts": {"provider_id": generate_uuid(), "provider_type": "aws"}}
    )
    host_with_subscription_manager_id = db_create_host(
        extra_data={"canonical_facts": {"subscription_manager_id": generate_uuid()}}
    )
    host_with_insights_id = db_create_host(extra_data={"canonical_facts": {"insights_id": generate_uuid()}})
    host_with_all_id_facts = db_create_host(
        extra_data={
            "canonical_facts": {
                "provider_id": generate_uuid(),
                "provider_type": "aws",
                "subscription_manager_id": generate_uuid(),
                "insights_id": generate_uuid(),
            }
        }
    )

    # We have to create the host with ID fact first to prevent ValidationException
    host_without_id_facts = db_create_host(extra_data={"canonical_facts": {"insights_id": generate_uuid()}})
    # Then we can update the canonical facts
    host_without_id_facts.canonical_facts = {"fqdn": generate_uuid()}
    db_create_host(host=host_without_id_facts)

    all_host_ids = {
        host_with_provider_id.id,
        host_with_subscription_manager_id.id,
        host_with_insights_id.id,
        host_with_all_id_facts.id,
        host_without_id_facts.id,
    }
    expected_host_ids = all_host_ids - {host_without_id_facts.id}

    run(
        config=init_config(),
        logger=mocker.Mock(),
        session=db.session,
        event_producer=event_producer_mock,  # type: ignore[arg-type]
        notifications_event_producer=event_producer_mock,  # type: ignore[arg-type]
        shutdown_handler=ShutdownHandler(),
        application=flask_app,
    )

    existing_hosts = db_get_hosts(list(all_host_ids)).all()
    assert len(existing_hosts) == 4
    assert {host.id for host in existing_hosts} == expected_host_ids
