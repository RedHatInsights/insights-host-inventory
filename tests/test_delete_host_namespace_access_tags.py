from collections.abc import Callable

from connexion import FlaskApp
from pytest_mock import MockerFixture

from app.models import Host
from app.models import db
from delete_host_namespace_access_tags import run


def test_delete_access_namespace_happy_path(
    flask_app: FlaskApp,
    db_create_host: Callable[..., Host],
    mocker: MockerFixture,
):
    db_create_host(extra_data={"tags": {"sat_iam": {"hash": "value1"}}})
    db_create_host(extra_data={"tags": {"ns1": {"key2": "value2"}, "sat_iam": {"hash": "value2"}}})

    run(
        logger=mocker.Mock(),
        session=db.session,
        application=flask_app,
    )

    access_tag_hosts = Host.query.filter(Host.tags.has_key("sat_iam")).all()
    assert len(access_tag_hosts) == 0
