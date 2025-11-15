from __future__ import annotations

import logging
import os
from collections.abc import Generator

import pytest
from iqe.base.application import Application
from iqe_notifications.utils.email_alert import NotificationsEmailAlert
from iqe_notifications.utils.email_utils import FindEmailOptions
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_tags
from iqe_host_inventory.utils.notifications_utils import check_event_log_registered
from iqe_host_inventory.utils.notifications_utils import get_email_recipient

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.backend,
    pytest.mark.skipif(
        "smoke" in os.getenv("ENV_FOR_DYNACONF", "").lower(),
        reason="We can get email notifications only in Stage and Prod",
    ),
]


@pytest.fixture(scope="module")
def setup_registered_notifications(application: Application) -> Generator[None]:
    """
    Creates Behavior Group (BG) in Notifications service.
    Check iqe-notifications-plugin README for more information.
    """

    email_alert = NotificationsEmailAlert(
        application, event_name="New system registered", bundle_name="rhel"
    )
    email_alert.notification_setup_before_trigger_event()

    yield

    email_alert.clean_up()


def check_instant_email(
    application: Application, display_name: str, host_id: str, base_url: str
) -> None:
    """
    Finds an email notification and checks the email content.
    `Notifications.email.find_email()` utility goes through all the emails in the inbox from newest
    to oldest and checks if the email subject and body contain the required data. If yes, it
    returns the email. If it can't find the email, it returns `None`. We can limit the number of
    emails it goes through via `email_amount` parameter. Also, we can set the number of retries and
    the timeout between the retries. I set the `email_amount` to a fairly small value, because we
    expect that our notification will be among the newest emails. Also, I set `retry_timeout` to 0,
    because the utility behaves in a weird way and if the timeout is non-zero, it adds 30 seconds
    to it on each retry and finding the emails takes a long time then. The email is not deleted
    after it is fetched and it is kept in the inbox.
    """
    email = application.notifications.email.find_email(
        options=FindEmailOptions(
            subject_token="Instant notification - New system registered - Inventory - "
            "Red Hat Enterprise Linux",
            body_token=display_name,
            email_amount=30,
            retry=30,
            retry_timeout=0,
        )
    )

    assert email is not None, "Couldn't find the email notification"
    assert "Inventory - Red Hat Enterprise Linux" in email.body
    assert "New system registered" in email.body
    assert (
        f'<strong><a target="_blank" href="{base_url}/insights/inventory/{host_id}">'
        f"{display_name}</a></strong> was registered in Inventory."
    ) in email.body
    assert (
        f'<a target="_blank" '
        f'href="{base_url}/insights/inventory/?from=notifications&integration=instant_email">'
        f"Open Inventory in Red Hat Lightspeed</a>" in email.body
    )


@pytest.mark.usefixtures("setup_registered_notifications")
@pytest.mark.parametrize(
    "host_inventory_test_app",
    [
        pytest.param(lf("host_inventory"), id="default auth"),
        pytest.param(lf("host_inventory_cert_auth"), id="cert auth"),
    ],
)
def test_notifications_e2e_registered(
    host_inventory: ApplicationHostInventory,
    hbi_base_url: str,
    host_inventory_test_app: ApplicationHostInventory,
):
    """
    Note: This test requires a specially configured user.
          Check "Notifications testing" section in the README.

    https://issues.redhat.com/browse/RHINENG-7918

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        title: Test email notification and event log after creating hosts
    """
    tags = generate_tags()
    host = host_inventory_test_app.upload.create_host(tags=tags)
    sp = host_inventory.apis.hosts.get_hosts_system_profile(host)[0].system_profile

    check_instant_email(
        host_inventory.application,
        display_name=host.display_name,
        host_id=host.id,
        base_url=hbi_base_url,
    )
    check_event_log_registered(host_inventory.application, host, tags, sp, base_url=hbi_base_url)


def test_notifications_e2e_registered_digest(
    application: Application,
    hbi_base_url: str,
):
    """
    The digest email is always sent at 00:00 UTC. This can be adjusted only by quarters of hour
    (the time has to be XX:00, XX:15, XX:30 or XX:45). Setting it to that value and then waiting
    for the digest would take a long time, so this test finds a digest from the last midnight and
    checks the content. Because the digest contains data from previous test runs, we can't check
    hosts display names.

    Note: This test requires a specially configured user.
          Check "Notifications testing" section in the README.

    https://issues.redhat.com/browse/RHINENG-7918

    metadata:
        requirements: inv-notifications-new-system-registered
        assignee: fstavela
        importance: high
        title: Test email notification digest after creating hosts
    """
    email = application.notifications.email.find_email(
        options=FindEmailOptions(
            subject_token="Daily digest - Red Hat Enterprise Linux",
            body_token="New systems registered",
            recipient_token=get_email_recipient(application, digest=True),
            email_amount=100,
            retry=1,
            retry_timeout=0,
        )
    )

    assert email is not None, "Couldn't find the email notification"
    assert "<h1>Daily digest - Red Hat Enterprise Linux</h1>" in email.body
    assert "<th>New system registered</th>" in email.body
    assert (
        '<a target="_blank" '
        f'href="{hbi_base_url}/insights/inventory/?from=notifications&integration=daily_digest">'
        "Open Inventory in Red Hat Lightspeed</a>" in email.body
    )
