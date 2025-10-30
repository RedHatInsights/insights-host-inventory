import pytest

from tests.helpers.outbox_utils import capture_outbox_calls as _capture


@pytest.fixture
def capture_outbox_calls_fixture():
    """
    Fixture returning a contextmanager that captures write_event_to_outbox calls.

    Usage:
        with capture_outbox_calls_fixture("api.host.write_event_to_outbox", capture_groups=True) as calls:
            ...
    """

    def _factory(target: str, capture_groups: bool = False):
        return _capture(target, capture_groups=capture_groups)

    return _factory
