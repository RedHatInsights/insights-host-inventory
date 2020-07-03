from datetime import timedelta

from app.models import Host
from app.utils import HostWrapper
from tests.test_api_utils import ACCOUNT
from tests.test_api_utils import ApiBaseTestCase
from tests.test_api_utils import db
from tests.test_api_utils import DbApiTestCase
from tests.test_api_utils import generate_uuid
from tests.test_api_utils import HOST_URL
from tests.test_api_utils import now


class CullingBaseTestCase(ApiBaseTestCase):
    def _nullify_culling_fields(self, host_id):
        with self.app.app_context():
            host = db.session.query(Host).get(host_id)
            host.stale_timestamp = None
            host.reporter = None
            db.session.add(host)
            db.session.commit()


class HostStalenessBaseTestCase(DbApiTestCase, CullingBaseTestCase):
    def _create_host(self, stale_timestamp):
        data = {
            "account": ACCOUNT,
            "insights_id": str(generate_uuid()),
            "facts": [{"facts": {"fact1": "value1"}, "namespace": "ns1"}],
        }
        if stale_timestamp:
            data["reporter"] = "some reporter"
            data["stale_timestamp"] = stale_timestamp.isoformat()

        host = HostWrapper(data)
        response = self.post(HOST_URL, [host.data()], 207)
        self._verify_host_status(response, 0, 201)
        return self._pluck_host_from_response(response, 0)

    def setUp(self):
        super().setUp()
        current_timestamp = now()
        self.fresh_host = self._create_host(current_timestamp + timedelta(hours=1))
        self.stale_host = self._create_host(current_timestamp - timedelta(hours=1))
        self.stale_warning_host = self._create_host(current_timestamp - timedelta(weeks=1, hours=1))
        self.culled_host = self._create_host(current_timestamp - timedelta(weeks=2, hours=1))

        self.unknown_host = self._create_host(current_timestamp)
        self._nullify_culling_fields(self.unknown_host["id"])
