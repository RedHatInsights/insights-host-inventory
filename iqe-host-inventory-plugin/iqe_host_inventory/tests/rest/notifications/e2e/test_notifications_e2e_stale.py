from __future__ import annotations

import logging
import os
from collections.abc import Generator

import pytest
from iqe.base.application import Application
from iqe_notifications.utils.email_alert import NotificationsEmailAlert
from iqe_notifications.utils.email_utils import FindEmailOptions

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_tags
from iqe_host_inventory.utils.notifications_utils import check_event_log_stale
from iqe_host_inventory.utils.staleness_utils import set_staleness

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.backend,
    pytest.mark.skipif(
        "smoke" in os.getenv("ENV_FOR_DYNACONF", "").lower(),
        reason="We can get email notifications only in Stage and Prod",
    ),
]


@pytest.fixture(scope="module")
def setup_stale_notifications(application: Application) -> Generator[None]:
    """
    Creates Behavior Group (BG) in Notifications service.
    Check iqe-notifications-plugin README for more information.
    """

    email_alert = NotificationsEmailAlert(
        application, event_name="System became stale", bundle_name="rhel"
    )
    email_alert.notification_setup_before_trigger_event()

    yield

    email_alert.clean_up()


def check_instant_email(
    application: Application,
    display_name: str,
    host_id: str,
    base_url: str,
    *,
    retry: int = 1,
    retry_timeout: int = 0,
) -> None:
    """
    Finds an email notification and checks the email content.

    The `Notifications.email.find_email()` utility goes through all the emails in the inbox
    from newest to oldest and checks if the email subject and body contain the required data.
    If yes, it returns the email. If no, it returns `None`.

    We can limit the number of emails it goes through via the `email_amount` parameter.  This
    parameter is set to a fairly small value because we expect that our notification will be
    among the newest emails.

    We can also set the number of retries and the timeout between the retries.  In the case of
    stale host notitications, in which stale host detection is performed hourly, we can use
    a combination of the retry and retry_timeout parameters to poll.

    The email is not deleted after it is fetched and is kept in the inbox.
    """
    email = application.notifications.email.find_email(
        options=FindEmailOptions(
            subject_token="Instant notification - System became stale - Inventory - "
            "Red Hat Enterprise Linux",
            body_token=display_name,
            email_amount=50,
            retry=retry,
            retry_timeout=retry_timeout,
        )
    )

    assert email is not None, "Couldn't find the email notification"
    assert "Inventory - Red Hat Enterprise Linux" in email.body
    assert "System became stale" in email.body
    assert f"{base_url}/insights/inventory/{host_id}" in email.body


@pytest.mark.extended
@pytest.mark.usefixtures("setup_stale_notifications")
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_notifications_e2e_stale(
    host_inventory: ApplicationHostInventory,
    hbi_base_url: str,
):
    """
    Notes:
        This test requires a specially configured user.  Check "Notifications testing"
        section in the README.

        This test can take up to an hour to run and thus should only run in the
        'extended' pipeline

    https://issues.redhat.com/browse/RHINENG-7916

    metadata:
        requirements: inv-notifications-system-became-stale
        assignee: msager
        importance: high
        title: Test email notification and event log when hosts become stale
    """
    tags = generate_tags()
    host = host_inventory.upload.create_host(tags=tags)
    sp = host_inventory.apis.hosts.get_hosts_system_profile(host)[0].system_profile

    deltas = (1, 3600, 7200)
    set_staleness(host_inventory, deltas)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="stale")

    check_instant_email(
        host_inventory.application,
        display_name=host.display_name,
        host_id=host.id,
        base_url=hbi_base_url,
        retry=20,
        retry_timeout=180,
    )
    check_event_log_stale(host_inventory.application, host, tags, sp, base_url=hbi_base_url)


@pytest.mark.skipif(
    "stage" not in os.getenv("ENV_FOR_DYNACONF", "stage_proxy").lower(),
    reason="Can't filter Prod emails from global account. This test should be moved to extended.",
)
@pytest.mark.usefixtures("setup_stale_notifications")
def test_notifications_e2e_stale_digest(
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

    https://issues.redhat.com/browse/RHINENG-7916

    metadata:
        requirements: inv-notifications-system-became-stale
        assignee: msager
        importance: high
        title: Test email notification digest when hosts become stale
    """
    email = application.notifications.email.find_email(
        options=FindEmailOptions(
            subject_token="Daily digest - Red Hat Enterprise Linux",
            body_token="Stale systems",
            recipient_token="stage",
            email_amount=100,
            retry=1,
            retry_timeout=0,
        )
    )

    assert email is not None, "Couldn't find the email notification"
    assert "Daily digest - Red Hat Enterprise Linux" in email.body
    assert "Stale system" in email.body
    assert f"{hbi_base_url}/insights/inventory/" in email.body
