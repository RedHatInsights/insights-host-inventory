import pytest

from app.config import Config
from app.config import RuntimeEnvironment
from app.payload_tracker import get_payload_tracker
from app.payload_tracker import init_payload_tracker
from tests.helpers.test_utils import now


@pytest.fixture(scope="function")
def payload_tracker():
    def _payload_tracker(account=None, org_id=None, request_id=None, producer=None):
        config = Config(RuntimeEnvironment.SERVER)
        init_payload_tracker(config, producer=producer)
        return get_payload_tracker(account=account, org_id=org_id, request_id=request_id)

    return _payload_tracker


@pytest.fixture(scope="function")
def tracker_datetime_mock(mocker):
    return mocker.patch("app.payload_tracker.datetime", **{"utcnow.return_value": now()})
